#!/usr/bin/env bash
# Stand up the Oracle Forms 12c "before" environment for this sample.
#
# The sample's deployable app is the modern "after". This script builds the
# LEGACY side — a WebLogic 12.2.1.4 + Forms Services domain that serves the
# ORDERS form (pipeline/sample-inputs/forms/ORDERS.fmb) against the same
# Oracle schema the modern API uses — so you can demo a true before/after on
# one dataset. See docs/FORMS_BEFORE_ENV.md for the full guide and gotchas.
#
# LICENSING — BRING YOUR OWN ORACLE BINARIES. This repo ships NO Oracle
# software. You need a licensed Oracle Fusion Middleware 12.2.1.4
# (Infrastructure + Forms & Reports) installation and an Oracle JDK 8 on the
# host before running any phase, plus rights to run Oracle XE (the free
# gvenzl/oracle-xe container is used ONLY as the WebLogic repository DB).
#
# Usage:
#   forms-setup.sh all              run every phase in order
#   forms-setup.sh <phase> [...]    run selected phases:
#                                   db rcu domain component config compile start
#
# Required environment (no defaults for secrets — export them first):
#   MW_HOME              Oracle Middleware home (e.g. /u01/app/oracle/product/fmw)
#   JDK_HOME             Oracle JDK 8 home (e.g. /u01/jdk)
#   DOMAIN_HOME          Domain to create (e.g. /u01/app/oracle/config/domains/forms_domain)
#   REPO_DB_PASSWORD     SYS/SYSTEM password for the local XE repository DB
#   RCU_SCHEMA_PASSWORD  password for all RCU schemas
#   WLS_ADMIN_PASSWORD   weblogic admin user password
#   APP_DB_HOST          host of the APPLICATION Oracle DB (the sample's DatabaseStack EC2)
#   APP_DB_SERVICE       service name of the application PDB (e.g. XEPDB1)
#   APP_DB_USER          application schema (e.g. app_data)
#   APP_DB_PASSWORD      application schema password (read it from Secrets Manager;
#                        never hardcode it)
# Optional:
#   RCU_PREFIX           RCU schema prefix                 (default FORMS)
#   DOMAIN_NAME          domain name                       (default basename of DOMAIN_HOME)
#   FORM_SOURCE          .fmb to compile and serve         (default <repo>/pipeline/sample-inputs/forms/ORDERS.fmb)
#   APP_DB_PORT          application DB listener port      (default 1521)
#   REPO_DB_IMAGE        repository DB container image     (default gvenzl/oracle-xe:21-slim)
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

: "${MW_HOME:?export MW_HOME (Oracle Middleware home)}"
: "${JDK_HOME:?export JDK_HOME (Oracle JDK 8 home)}"
: "${DOMAIN_HOME:?export DOMAIN_HOME (domain directory to create)}"

RCU_PREFIX="${RCU_PREFIX:-FORMS}"
DOMAIN_NAME="${DOMAIN_NAME:-$(basename "$DOMAIN_HOME")}"
FORM_SOURCE="${FORM_SOURCE:-$ROOT/pipeline/sample-inputs/forms/ORDERS.fmb}"
APP_DB_PORT="${APP_DB_PORT:-1521}"
REPO_DB_IMAGE="${REPO_DB_IMAGE:-gvenzl/oracle-xe:21-slim}"

FMWCONFIG="$DOMAIN_HOME/config/fmwconfig"
FORMS_INSTANCE_DIR="$FMWCONFIG/components/FORMS/forms1"

log() { echo -e "\n=== forms-setup: $* ==="; }

# ----------------------------------------------------------------------------
# db — local Oracle XE container: the WebLogic repository (RCU/OPSS) database.
# The APPLICATION data lives in the sample's DatabaseStack DB, not here.
# ----------------------------------------------------------------------------
phase_db() {
  log "repository DB (XE container)"
  : "${REPO_DB_PASSWORD:?export REPO_DB_PASSWORD}"
  command -v docker >/dev/null || { echo "docker is required"; exit 1; }
  if ! docker ps -a --format '{{.Names}}' | grep -q '^formsrepo$'; then
    docker run -d --name formsrepo --restart unless-stopped -p 1521:1521 \
      -e ORACLE_PASSWORD="$REPO_DB_PASSWORD" \
      -v formsrepo_data:/opt/oracle/oradata "$REPO_DB_IMAGE"
  else
    docker start formsrepo >/dev/null
  fi
  echo "waiting for the repository DB to accept connections..."
  # Probe with a distinctive marker: sqlplus prints ORA- errors to stdout, and
  # common ones (ORA-01017 wrong password, ORA-12541 no listener) contain the
  # digit 1 — a bare `grep -q 1` would declare the DB "up" on a failed login.
  for _ in $(seq 1 60); do
    docker exec formsrepo bash -c \
      "echo \"select 'DB_READY' from dual;\" | sqlplus -s system/$REPO_DB_PASSWORD@localhost/XEPDB1" \
      2>/dev/null | grep -q DB_READY && { echo "repository DB is up"; return; }
    sleep 5
  done
  echo "repository DB did not come up"; exit 1
}

# ----------------------------------------------------------------------------
# rcu — create the JRF repository schemas the Forms domain requires.
# NOTE the flag is -useSamePasswordForAllSchemaUsers (not ...Schemas).
# ----------------------------------------------------------------------------
phase_rcu() {
  log "RCU schemas (prefix $RCU_PREFIX)"
  : "${REPO_DB_PASSWORD:?export REPO_DB_PASSWORD}"
  : "${RCU_SCHEMA_PASSWORD:?export RCU_SCHEMA_PASSWORD}"
  printf '%s\n%s\n' "$REPO_DB_PASSWORD" "$RCU_SCHEMA_PASSWORD" | \
  "$MW_HOME/oracle_common/bin/rcu" -silent -createRepository \
    -databaseType ORACLE -connectString localhost:1521/XEPDB1 \
    -dbUser SYS -dbRole SYSDBA -schemaPrefix "$RCU_PREFIX" \
    -component STB -component OPSS -component IAU -component IAU_APPEND \
    -component IAU_VIEWER -component WLS -component WLS_RUNTIME -component MDS \
    -useSamePasswordForAllSchemaUsers true
}

# ----------------------------------------------------------------------------
# domain — WLST-offline domain from the WLS + JRF + EM + Forms templates.
# A FRESHLY created JRF domain initializes its (empty) OPSS DB security store
# on first boot — never clone a domain away from its repository DB.
# ----------------------------------------------------------------------------
phase_domain() {
  log "WebLogic domain $DOMAIN_NAME"
  : "${RCU_SCHEMA_PASSWORD:?export RCU_SCHEMA_PASSWORD}"
  : "${WLS_ADMIN_PASSWORD:?export WLS_ADMIN_PASSWORD}"
  local build_py; build_py="$(mktemp /tmp/forms_domain_build.XXXX.py)"
  cat > "$build_py" <<PYEOF
import os
mw = os.environ['MW_HOME']
readTemplate(mw + '/wlserver/common/templates/wls/wls.jar')
addTemplate(mw + '/oracle_common/common/templates/wls/oracle.jrf_template.jar')
addTemplate(mw + '/em/common/templates/wls/oracle.em_wls_template.jar')
addTemplate(mw + '/forms/common/templates/wls/forms_template.jar')
setOption('ServerStartMode', 'dev')
cd('/Security/base_domain/User/weblogic')
cmo.setPassword(os.environ['WLS_ADMIN_PASSWORD'])
# Point the service-table datasource at the RCU schemas, then let WLST derive
# every other JRF datasource from it.
cd('/JDBCSystemResource/LocalSvcTblDataSource/JdbcResource/LocalSvcTblDataSource/JDBCDriverParams/NO_NAME_0')
set('URL', 'jdbc:oracle:thin:@//localhost:1521/XEPDB1')
set('DriverName', 'oracle.jdbc.OracleDriver')
set('PasswordEncrypted', os.environ['RCU_SCHEMA_PASSWORD'])
cd('Properties/NO_NAME_0/Property/user')
set('Value', os.environ['RCU_PREFIX'] + '_STB')
getDatabaseDefaults()
writeDomain(os.environ['DOMAIN_HOME'])
closeTemplate()
# WLST may print "Error: No domain has been read" during JRF post-steps here.
# It is benign: the domain HAS been written.
PYEOF
  MW_HOME="$MW_HOME" DOMAIN_HOME="$DOMAIN_HOME" RCU_PREFIX="$RCU_PREFIX" \
  RCU_SCHEMA_PASSWORD="$RCU_SCHEMA_PASSWORD" WLS_ADMIN_PASSWORD="$WLS_ADMIN_PASSWORD" \
  JAVA_HOME="$JDK_HOME" "$MW_HOME/oracle_common/common/bin/wlst.sh" "$build_py"
  rm -f "$build_py"

  # boot.properties for unattended starts (WLS encrypts them on first boot)
  local s
  for s in AdminServer WLS_FORMS; do
    mkdir -p "$DOMAIN_HOME/servers/$s/security"
    printf 'username=weblogic\npassword=%s\n' "$WLS_ADMIN_PASSWORD" \
      > "$DOMAIN_HOME/servers/$s/security/boot.properties"
  done
}

# ----------------------------------------------------------------------------
# component — a template-built domain ships an INCOMPLETE Forms component
# instance: populate its server config from the product templates and fix the
# instance paths in default.env, or the servlet fails at runtime.
# ----------------------------------------------------------------------------
phase_component() {
  log "FORMS component instance"
  mkdir -p "$FORMS_INSTANCE_DIR/server"
  cp -rn "$MW_HOME/forms/templates/config/." "$FORMS_INSTANCE_DIR/server/"
  local env_file="$FORMS_INSTANCE_DIR/server/default.env"
  [ -f "$env_file" ] || { echo "default.env not found under $FORMS_INSTANCE_DIR/server"; exit 1; }
  # The template writes components/FORMS/instances/forms1 — the real path has
  # no "instances" segment.
  sed -i "s|components/FORMS/instances/forms1|components/FORMS/forms1|g" "$env_file"
  grep -q '^FORMS_INSTANCE=' "$env_file" || echo "FORMS_INSTANCE=$FORMS_INSTANCE_DIR" >> "$env_file"
  grep -q "^FORMS_PATH=.*$MW_HOME/forms" "$env_file" || echo "FORMS_PATH=$MW_HOME/forms" >> "$env_file"
}

# ----------------------------------------------------------------------------
# config — TNS alias for the APPLICATION DB + the [orders] servlet config.
# Every base-file parameter MUST be an ABSOLUTE path: relative names raise
# FRM-93131 (base HTML) / FRM-93136 (base TXT for the standalone launcher).
# ----------------------------------------------------------------------------
phase_config() {
  log "tnsnames + formsweb.cfg [orders]"
  : "${APP_DB_HOST:?export APP_DB_HOST}"
  : "${APP_DB_SERVICE:?export APP_DB_SERVICE}"
  : "${APP_DB_USER:?export APP_DB_USER}"
  : "${APP_DB_PASSWORD:?export APP_DB_PASSWORD (from Secrets Manager)}"

  if ! grep -q '^APPDB' "$FMWCONFIG/tnsnames.ora" 2>/dev/null; then
    cat >> "$FMWCONFIG/tnsnames.ora" <<TNSEOF
APPDB =
  (DESCRIPTION =
    (ADDRESS = (PROTOCOL = TCP)(HOST = $APP_DB_HOST)(PORT = $APP_DB_PORT))
    (CONNECT_DATA = (SERVICE_NAME = $APP_DB_SERVICE))
  )
TNSEOF
  fi

  local cfg="$FORMS_INSTANCE_DIR/server/formsweb.cfg"
  if ! grep -q '^\[orders\]' "$cfg"; then
    cat >> "$cfg" <<CFGEOF

[orders]
form=ORDERS.fmx
userid=$APP_DB_USER/$APP_DB_PASSWORD@APPDB
baseHTML=$FORMS_INSTANCE_DIR/server/base.htm
baseHTMLjpi=$FORMS_INSTANCE_DIR/server/basejpi.htm
baseSAAfile=$FORMS_INSTANCE_DIR/server/basesaa.txt
term=$MW_HOME/forms/fmrweb.res
CFGEOF
  fi
  echo "NOTE: formsweb.cfg now embeds the application DB credential — keep the"
  echo "      host locked down; the Forms runtime prompts for logon regardless."
}

# ----------------------------------------------------------------------------
# compile — frmcmp_batch needs FORMS_INSTANCE and a terminal type or it dies
# with the generic FRM-91500. Compile validates every trigger against the
# live application schema (the pkg_pricing / pkg_orders packages must exist —
# they are created by infrastructure/seed-sql/app_data_packages.sql).
# ----------------------------------------------------------------------------
phase_compile() {
  log "compile $(basename "$FORM_SOURCE")"
  : "${APP_DB_USER:?export APP_DB_USER}"; : "${APP_DB_PASSWORD:?export APP_DB_PASSWORD}"
  [ -f "$FORM_SOURCE" ] || { echo "form source not found: $FORM_SOURCE"; exit 1; }
  local build_dir; build_dir="$(mktemp -d /tmp/formsbuild.XXXX)"
  cp "$FORM_SOURCE" "$build_dir/ORDERS.fmb"
  (
    cd "$build_dir"
    export ORACLE_HOME="$MW_HOME" JAVA_HOME="$JDK_HOME"
    export FORMS_INSTANCE="$FORMS_INSTANCE_DIR"
    export TNS_ADMIN="$FMWCONFIG"
    export TERM=vt220 ORACLE_TERM=vt220
    "$MW_HOME/bin/frmcmp_batch" module=ORDERS.fmb \
      userid="$APP_DB_USER/$APP_DB_PASSWORD@APPDB" \
      module_type=form compile_all=yes output_file=ORDERS.fmx </dev/null
  )
  cp "$build_dir/ORDERS.fmx" "$MW_HOME/forms/ORDERS.fmx"
  rm -rf "$build_dir"
  echo "deployed $MW_HOME/forms/ORDERS.fmx"
}

# ----------------------------------------------------------------------------
# start — AdminServer, then the WLS_FORMS managed server; verify the servlet.
# ----------------------------------------------------------------------------
phase_start() {
  log "start WebLogic"
  export JAVA_HOME="$JDK_HOME"
  if ! curl -sf -o /dev/null http://localhost:7001/console; then
    nohup "$DOMAIN_HOME/bin/startWebLogic.sh" > "$DOMAIN_HOME/admin.out" 2>&1 &
    for _ in $(seq 1 90); do
      curl -s -o /dev/null -w '%{http_code}' http://localhost:7001/console 2>/dev/null \
        | grep -q '200\|302' && break
      sleep 5
    done
  fi
  if ! curl -s http://localhost:9001/forms/frmservlet 2>/dev/null | grep -qi forms; then
    nohup "$DOMAIN_HOME/bin/startManagedWebLogic.sh" WLS_FORMS http://localhost:7001 \
      > "$DOMAIN_HOME/wls_forms.out" 2>&1 &
    for _ in $(seq 1 90); do
      curl -s http://localhost:9001/forms/frmservlet 2>/dev/null | grep -qi forms && break
      sleep 5
    done
  fi
  curl -s -o /dev/null -w 'frmservlet?config=orders -> HTTP %{http_code}\n' \
    'http://localhost:9001/forms/frmservlet?config=orders'
}

# ----------------------------------------------------------------------------
main() {
  [ $# -ge 1 ] || { grep '^#' "$0" | head -40; exit 1; }
  local phases=("$@")
  [ "${phases[0]}" = "all" ] && phases=(db rcu domain component config compile start)
  local p
  for p in "${phases[@]}"; do
    case "$p" in
      db|rcu|domain|component|config|compile|start) "phase_$p" ;;
      *) echo "unknown phase: $p (valid: db rcu domain component config compile start)"; exit 1 ;;
    esac
  done
  log "done"
}
main "$@"
