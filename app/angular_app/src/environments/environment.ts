// API base URL. Overwritten at build time by scripts/05_deploy_apps.sh, which
// sed-replaces __API_BASE_URL__ with the ALB DNS name from the ApiStack output.
export const environment = {
  production: true,
  apiBaseUrl: '__API_BASE_URL__',
};
