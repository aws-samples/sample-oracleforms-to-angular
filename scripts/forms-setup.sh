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
#                                   db rcu domain component config compile relink start
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
#   MOTIF_LIB_DIR        directory holding libXm.so.4 / libXp.so.6 on hosts whose
#                        distro does not package Motif (see docs/FORMS_BEFORE_ENV.md)
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
# The Forms servlet does NOT read the component-instance config above: on a
# template-built domain it reads the per-server application copy below. Config
# phases must maintain BOTH (the component copy feeds frmcmp_batch/dev tools).
SERVLET_CONFIG_DIR="$FMWCONFIG/servers/WLS_FORMS/applications/formsapp_12.2.1/config"

log() { echo -e "\n=== forms-setup: $* ==="; }

append_orders_section() {
  : "${APP_DB_USER:?export APP_DB_USER}"; : "${APP_DB_PASSWORD:?export APP_DB_PASSWORD}"
  cat >> "$1" <<CFGEOF

[orders]
form=ORDERS.fmx
userid=$APP_DB_USER/$APP_DB_PASSWORD@APPDB
baseHTML=$FORMS_INSTANCE_DIR/server/base.htm
baseHTMLjpi=$FORMS_INSTANCE_DIR/server/basejpi.htm
baseSAAfile=$FORMS_INSTANCE_DIR/server/basesaa.txt
term=$MW_HOME/forms/fmrweb.res
CFGEOF
}

# The per-server servlet config (SERVLET_CONFIG_DIR) is MATERIALIZED BY THE
# DOMAIN'S FIRST BOOT — pre-boot phases cannot fully patch it. Called from
# phase_config (covers re-runs on a booted domain) and from phase_start after
# the servers are up; formsweb.cfg/default.env are read per Forms session, so
# post-boot patching needs no restart.
patch_servlet_config() {
  [ -d "$SERVLET_CONFIG_DIR" ] || return 0
  [ -f "$SERVLET_CONFIG_DIR/default.env" ] && \
    sed -i "s|components/FORMS/instances/forms1|components/FORMS/forms1|g" \
      "$SERVLET_CONFIG_DIR/default.env"
  local cfg="$SERVLET_CONFIG_DIR/formsweb.cfg"
  if [ -f "$cfg" ] && ! grep -q '^\[orders\]' "$cfg"; then
    append_orders_section "$cfg"
  fi
}

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
    -component IAU_VIEWER -component WLS -component MDS \
    -useSamePasswordForAllSchemaUsers true
  # NOTE: WLS_RUNTIME is NOT an RCU component (RCU-6065 if passed) — the WLS
  # component creates the <prefix>_WLS_RUNTIME schema itself.
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

  # The formsapp lifecycle listener loads Forms native libraries at server
  # start (libifopmnwrp -> libopmnperf under oracle_common/lib). A template
  # domain does not put them on the server library path, so formsapp fails to
  # activate (BEA-149231 UnsatisfiedLinkError) without this override.
  cat > "$DOMAIN_HOME/bin/setUserOverrides.sh" <<OVREOF
export LD_LIBRARY_PATH="$MW_HOME/lib:$MW_HOME/oracle_common/lib:\${LD_LIBRARY_PATH:-}"
OVREOF
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
  # no "instances" segment. The servlet's own default.env (SERVLET_CONFIG_DIR)
  # ships with the same broken path; fix both.
  local f
  for f in "$env_file" "$SERVLET_CONFIG_DIR/default.env"; do
    [ -f "$f" ] && sed -i "s|components/FORMS/instances/forms1|components/FORMS/forms1|g" "$f"
  done
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

  # The servlet serves SERVLET_CONFIG_DIR/formsweb.cfg, NOT the component copy
  # — an [orders] section only in the component file yields FRM-93131 with the
  # default (relative) base HTML names. The servlet copy is only materialized
  # by the domain's FIRST boot, so phase_start patches it again post-boot.
  local cfg
  for cfg in "$FORMS_INSTANCE_DIR/server/formsweb.cfg" "$SERVLET_CONFIG_DIR/formsweb.cfg"; do
    [ -f "$cfg" ] || continue
    grep -q '^\[orders\]' "$cfg" || append_orders_section "$cfg"
  done
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
    # frmcmp_batch resolves libig/libclntsh from $MW_HOME/lib — without this
    # it dies on "libig.so.0: cannot open shared object file".
    export LD_LIBRARY_PATH="$MW_HOME/lib:${LD_LIBRARY_PATH:-}"
    "$MW_HOME/bin/frmcmp_batch" module=ORDERS.fmb \
      userid="$APP_DB_USER/$APP_DB_PASSWORD@APPDB" \
      module_type=form compile_all=yes output_file=ORDERS.fmx </dev/null
  )
  cp "$build_dir/ORDERS.fmx" "$MW_HOME/forms/ORDERS.fmx"
  rm -rf "$build_dir"
  echo "deployed $MW_HOME/forms/ORDERS.fmx"
}

# ----------------------------------------------------------------------------
# relink — a fresh 12.2.1.4 Forms & Reports install ships a frmweb that
# references shared libraries (libiffw.so.0 ...) that exist NOWHERE on disk;
# the binary must be relinked once (make -f ins_forms.mk frmweb_install).
# libclntshcore is also absent from $MW_HOME/lib (the only copy hides under
# OPatch's .patch_storage). At runtime the servlet spawns frmweb with
# default.env's LD_LIBRARY_PATH — which lists ONLY $MW_HOME/lib — so every
# non-system dependency must resolve from that one directory.
# ----------------------------------------------------------------------------
phase_relink() {
  log "frmweb native libraries / relink"
  if [ ! -e "$MW_HOME/lib/libclntshcore.so.12.1" ]; then
    local core
    core="$(find "$MW_HOME/.patch_storage" -name libclntshcore.so.12.1 2>/dev/null | head -1)"
    [ -n "$core" ] || { echo "libclntshcore.so.12.1 not found anywhere under $MW_HOME"; exit 1; }
    cp "$core" "$MW_HOME/lib/"
  fi
  ln -sf libclntshcore.so.12.1 "$MW_HOME/lib/libclntshcore.so"
  ln -sf ../oracle_common/lib/libopmnperf.so "$MW_HOME/lib/libopmnperf.so"
  ln -sf ../oracle_common/lib/libons.so "$MW_HOME/lib/libons.so"
  # Motif: link libXm/libXp into $MW_HOME/lib when the distro doesn't package
  # them (Amazon Linux 2023 doesn't — see docs/FORMS_BEFORE_ENV.md).
  if [ -n "${MOTIF_LIB_DIR:-}" ]; then
    ln -sf "$MOTIF_LIB_DIR"/libXm.so.4* "$MW_HOME/lib/"
    ln -sf "$MOTIF_LIB_DIR"/libXp.so.6* "$MW_HOME/lib/"
  fi
  # DO NOT register these directories in ld.so.conf: Oracle's own libexpat.so.1
  # would shadow the system one and break python/pyexpat consumers (aws CLI).
  export LD_LIBRARY_PATH="$MW_HOME/lib:$MW_HOME/oracle_common/lib:${MOTIF_LIB_DIR:+$MOTIF_LIB_DIR:}${LD_LIBRARY_PATH:-}"
  if ldd "$MW_HOME/bin/frmweb" 2>/dev/null | grep -q 'not found'; then
    command -v gcc >/dev/null || { echo "gcc is required to relink frmweb"; exit 1; }
    echo 'int main(){return 0;}' | gcc -x c - -o /dev/null \
      ${MOTIF_LIB_DIR:+-L"$MOTIF_LIB_DIR"} -lXm -lXp -lX11 2>/dev/null \
      || { echo "linkable Motif/X11 libraries required (libXm.so, libXp.so, libX11.so)"; exit 1; }
    # Old link lines may reference glibc's retired libpthread_nonshared.a.
    [ -e /usr/lib64/libpthread_nonshared.a ] || ar cr /usr/lib64/libpthread_nonshared.a 2>/dev/null || true
    ( cd "$MW_HOME/forms/lib" && \
      ORACLE_HOME="$MW_HOME" ${MOTIF_LIB_DIR:+LIBRARY_PATH="$MOTIF_LIB_DIR:${LIBRARY_PATH:-}"} \
      make -f ins_forms.mk frmweb_install )
  fi
  ldd "$MW_HOME/bin/frmweb" | grep -q 'not found' \
    && { echo "frmweb still has unresolved libraries:"; ldd "$MW_HOME/bin/frmweb" | grep 'not found'; exit 1; }
  # Simulate the servlet's spawn environment ($MW_HOME/lib only). A healthy
  # client-less frmweb prints FRM-91299 ("unable to create a connection to the
  # Java client") — anything else means the runtime cannot start.
  local out
  out="$( (ORACLE_HOME="$MW_HOME" LD_LIBRARY_PATH="$MW_HOME/lib" \
           FORMS_INSTANCE="$FORMS_INSTANCE_DIR" \
           TERM=vt220 ORACLE_TERM=vt220 timeout 10 "$MW_HOME/bin/frmweb" 2>&1 || true) | head -2 )"
  echo "$out" | grep -q 'FRM-91299' \
    || { echo "frmweb failed under the servlet's runtime library path: $out"; exit 1; }
  echo "frmweb runtime OK (resolves fully from $MW_HOME/lib)"
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
  # The first boot materializes the per-server servlet config — patch it now
  # (idempotent; per-session reads mean no restart is needed).
  patch_servlet_config

  # Forms error pages come back as HTTP 200 with an FRM-xxxxx body — a status
  # code alone proves nothing. Fail loudly unless the bootstrap page is clean.
  local body code
  body="$(mktemp)"
  code="$(curl -s -o "$body" -w '%{http_code}' 'http://localhost:9001/forms/frmservlet?config=orders')"
  if [ "$code" != "200" ] || grep -q 'FRM-' "$body"; then
    echo "frmservlet?config=orders is NOT healthy (HTTP $code):"
    head -5 "$body"; rm -f "$body"; exit 1
  fi
  rm -f "$body"
  echo "frmservlet?config=orders -> HTTP 200, no FRM errors"
}

# ----------------------------------------------------------------------------
main() {
  [ $# -ge 1 ] || { grep '^#' "$0" | head -40; exit 1; }
  local phases=("$@")
  [ "${phases[0]}" = "all" ] && phases=(db rcu domain component config compile relink start)
  local p
  for p in "${phases[@]}"; do
    case "$p" in
      db|rcu|domain|component|config|compile|relink|start) "phase_$p" ;;
      *) echo "unknown phase: $p (valid: db rcu domain component config compile relink start)"; exit 1 ;;
    esac
  done
  log "done"
}
main "$@"
