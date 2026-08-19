// Oracle modernization sample — .NET 8 Web API
//
// Provides two endpoint groups:
//   /api/accounts  — modern "after" of an APEX Opportunities CRM Account Details page
//   /api/reports   — generic config-driven endpoint for migrated Oracle Interactive Reports
//
// The Oracle connection is configured entirely via environment variables (ORACLE_HOST,
// ORACLE_PORT, ORACLE_SERVICE, ORACLE_USER, ORACLE_PASSWORD) so no credentials are
// baked into the image. In production these are injected by the Fargate task definition
// from AWS Secrets Manager.

using System.Data;
using Dapper;
using Oracle.ManagedDataAccess.Client;
using ModernApi.Services;

var builder = WebApplication.CreateBuilder(args);

// Build the Oracle connection string from environment variables injected by the
// Fargate task definition (ORACLE_* + the secret-sourced user/password).
string host = Environment.GetEnvironmentVariable("ORACLE_HOST") ?? "localhost";
string port = Environment.GetEnvironmentVariable("ORACLE_PORT") ?? "1521";
string service = Environment.GetEnvironmentVariable("ORACLE_SERVICE") ?? "XEPDB1";
string user = Environment.GetEnvironmentVariable("ORACLE_USER") ?? "app_user";
string pwd = Environment.GetEnvironmentVariable("ORACLE_PASSWORD") ?? "";

// EZCONNECT form: host:port/service. Service MUST be XEPDB1 (the XE PDB), not ORCL.
string connString =
    $"User Id={user};Password={pwd};Data Source={host}:{port}/{service};";

builder.Services.AddSingleton<IDbConnectionFactory>(
    new OracleConnectionFactory(connString));
builder.Services.AddScoped<IAccountService, AccountService>();
builder.Services.AddScoped<IReportService, ReportService>();
builder.Services.AddControllers();
builder.Services.AddEndpointsApiExplorer();
builder.Services.AddSwaggerGen();
builder.Services.AddCors(o => o.AddDefaultPolicy(p =>
    p.AllowAnyOrigin().AllowAnyHeader().AllowAnyMethod()));  // sample: open CORS

var app = builder.Build();

app.UseSwagger();
app.UseSwaggerUI();
app.UseCors();
app.MapControllers();

// Liveness/readiness: the ALB health check hits this; it verifies Oracle too.
app.MapGet("/health", async (IDbConnectionFactory factory) =>
{
    try
    {
        using IDbConnection conn = factory.Create();
        var one = await conn.ExecuteScalarAsync<int>("SELECT 1 FROM dual");
        return Results.Ok(new { status = "healthy", oracle = one == 1 });
    }
    catch (Exception ex)
    {
        return Results.Json(new { status = "unhealthy", error = ex.Message },
            statusCode: 503);
    }
});

app.Run();
