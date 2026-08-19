using System.Data;
using System.Text.RegularExpressions;
using Dapper;
using ModernApi.Models;

namespace ModernApi.Services;

// Generic, config-driven Reports API. It serves any report registered in the
// report_registry table — the migration pipeline writes a registry row for each
// Oracle Interactive Report it converts, so new report pages go live with zero
// backend redeploy (the pipeline just inserts a row and ships the Angular grid).
//
// Each registry row carries:
//   base_sql     : the allowlisted SELECT recovered from the APEX IR region
//   columns_json : [{"key","label","sortable","type"}] describing the grid columns
// Sort is applied server-side and ONLY against allowlisted column keys — user
// input is never interpolated into SQL.
public interface IReportService
{
    Task<IEnumerable<ReportDef>> ListReportsAsync();
    Task<ReportDef?> GetReportAsync(string key);
    Task<ReportData?> RunReportAsync(string key, string? sort, string? dir);
}

public sealed class ReportService : IReportService
{
    private readonly IDbConnectionFactory _factory;
    public ReportService(IDbConnectionFactory factory) => _factory = factory;

    public async Task<IEnumerable<ReportDef>> ListReportsAsync()
    {
        using var conn = _factory.Create();
        return await conn.QueryAsync<ReportDef>(
            "SELECT report_key AS Key, title AS Title, columns_json AS ColumnsJson, " +
            "source_page AS SourcePage FROM app_data.report_registry ORDER BY title");
    }

    public async Task<ReportDef?> GetReportAsync(string key)
    {
        using var conn = _factory.Create();
        return await conn.QueryFirstOrDefaultAsync<ReportDef>(
            "SELECT report_key AS Key, title AS Title, base_sql AS BaseSql, " +
            "columns_json AS ColumnsJson, source_page AS SourcePage " +
            "FROM app_data.report_registry WHERE report_key = :key", new { key });
    }

    public async Task<ReportData?> RunReportAsync(string key, string? sort, string? dir)
    {
        var def = await GetReportAsync(key);
        if (def is null) return null;

        // allowlist: sort only by a column the registry declares
        var jsonOpts = new System.Text.Json.JsonSerializerOptions
            { PropertyNameCaseInsensitive = true };
        var cols = System.Text.Json.JsonSerializer.Deserialize<List<ReportColumn>>(
                       def.ColumnsJson ?? "[]", jsonOpts) ?? new();
        var allowed = cols.Select(c => c.Key!).ToHashSet(StringComparer.OrdinalIgnoreCase);

        var sql = $"SELECT * FROM ({def.BaseSql})";
        if (!string.IsNullOrWhiteSpace(sort) && allowed.Contains(sort))
        {
            var d = string.Equals(dir, "desc", StringComparison.OrdinalIgnoreCase) ? "DESC" : "ASC";
            // sort is validated against the allowlist above; safe to embed
            sql += $" ORDER BY {sort} {d}";
        }

        using var conn = _factory.Create();
        var rows = (await conn.QueryAsync(sql)).Cast<IDictionary<string, object>>().ToList();
        return new ReportData(def.Title, cols, rows);
    }
}
