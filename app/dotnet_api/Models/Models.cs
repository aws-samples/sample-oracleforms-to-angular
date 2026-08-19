namespace ModernApi.Models;

// ── APEX Opportunities CRM — Account Details (modern "after") ─────────────────
// Reads/writes the EBA sales tables that the legacy APEX Account Details page
// uses. Property names map to the Oracle columns.
public sealed class Account
{
    // NUMBER key: the EBA/APEX insert trigger generates 39-digit synthetic keys
    // (~1e38) that overflow Int64 AND .NET decimal, so carry the id as a string.
    public string? Id { get; set; }
    public string? CustomerName { get; set; }
    public string? Tags { get; set; }
    public string? CustomerWebSite { get; set; }
    public string? CustomerLinkedin { get; set; }
    public string? CustomerFacebook { get; set; }
    public string? CustomerTwitter { get; set; }
    public string? CustomerTerritoryId { get; set; }
}

// Request body for create/update. Same fields the APEX P3_* items bind to.
public sealed class AccountInput
{
    public string? CustomerName { get; set; }
    public string? Tags { get; set; }
    public string? CustomerWebSite { get; set; }
    public string? CustomerLinkedin { get; set; }
    public string? CustomerFacebook { get; set; }
    public string? CustomerTwitter { get; set; }
    public string? CustomerTerritoryId { get; set; }
}

// Result of a save: Ok=false with the ordered legacy error strings when a
// recovered APEX validation fails (mirrors ValidationErrorResponse in the spec).
public record AccountSaveResult(bool Ok, string? Id, List<string> Errors);

// Territory LOV for the required-territory field (mirrors the APEX popup LOV).
public sealed class Territory
{
    public string? Id { get; set; }
    public string? Name { get; set; }
}

// ── Generic config-driven Reports (migrated Oracle Interactive Reports) ────────
// A report definition row from the report registry table.
public sealed class ReportDef
{
    public string? Key { get; set; }
    public string? Title { get; set; }
    public string? BaseSql { get; set; }
    public string? ColumnsJson { get; set; }
    public int? SourcePage { get; set; }
}

public sealed class ReportColumn
{
    public string? Key { get; set; }
    public string? Label { get; set; }
    public bool Sortable { get; set; } = true;
    public string? Type { get; set; }
    public bool Hidden { get; set; }
}

// Payload returned to the Angular grid: title + column defs + the data rows.
public record ReportData(string? Title, List<ReportColumn> Columns,
                         List<IDictionary<string, object>> Rows);
