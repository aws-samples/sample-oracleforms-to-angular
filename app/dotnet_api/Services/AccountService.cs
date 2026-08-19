using System.Data;
using System.Text.RegularExpressions;
using Dapper;
using Oracle.ManagedDataAccess.Client;
using ModernApi.Models;

namespace ModernApi.Services;

// Shared Oracle connection factory used by all services.
public interface IDbConnectionFactory
{
    IDbConnection Create();
}

public sealed class OracleConnectionFactory : IDbConnectionFactory
{
    private readonly string _connString;
    public OracleConnectionFactory(string connString) => _connString = connString;
    public IDbConnection Create() => new OracleConnection(_connString);
}

// Backs the modern "after" of the APEX Opportunities CRM Account Details page.
// Reads/writes the EBA sales tables — the same tables the legacy APEX app uses —
// so the before (APEX) and after (Angular/.NET) run on identical data.
//
// Every validation below is a rule recovered by the migration pipeline from the
// APEX export and preserved exactly, including quirks:
//   * duplicate name is case-insensitive and excludes self (NOT_EXISTS validation)
//   * tag blocklist rejects : ; # \ / ? &  (the '#' is rejected even though the
//     legacy error message never lists it — preserved bug-for-bug)
//   * URL fields must start with "http", case-sensitive (substr(x,1,4)='http'),
//     and null/empty passes (APEX EXPRESSION validations only fire when a value
//     is present)
//
// NOTE: the EBA/APEX insert trigger generates 39-digit synthetic keys (~1e38)
// that overflow Int64 AND .NET decimal, so ids are handled as STRINGS end to end
// (TO_CHAR in SQL, string in the model).
public interface IAccountService
{
    Task<IEnumerable<Account>> ListAsync(string? search);
    Task<IEnumerable<Territory>> ListTerritoriesAsync();
    Task<Account?> GetAsync(string id);
    Task<bool> IsNameTakenAsync(string customerName, string? excludeId);
    Task<AccountSaveResult> CreateAsync(AccountInput input);
    Task<AccountSaveResult> UpdateAsync(string id, AccountInput input);
}

public sealed class AccountService : IAccountService
{
    private readonly IDbConnectionFactory _factory;
    public AccountService(IDbConnectionFactory factory) => _factory = factory;

    private const string TABLE = "apex_sample.eba_sales_customers";

    // id is a huge NUMBER; select it as text so ODP.NET marshals it safely.
    private const string COLS =
        @"TO_CHAR(id) AS Id, customer_name AS CustomerName, tags AS Tags,
          customer_web_site AS CustomerWebSite, customer_linkedin AS CustomerLinkedin,
          customer_facebook AS CustomerFacebook, customer_twitter AS CustomerTwitter,
          TO_CHAR(customer_territory_id) AS CustomerTerritoryId";

    // Legacy: not regexp_like( :P3_TAGS, '[:;#\/\\\?\&]' )  -> reject if any present.
    private static readonly Regex InvalidTagChars = new(@"[:;#/\\?&]", RegexOptions.Compiled);

    // Legacy: substr(:PX, 1, 4) = 'http'  (case-sensitive; null/empty passes).
    private static bool StartsWithHttp(string? v)
        => string.IsNullOrEmpty(v) || (v.Length >= 4 && v.Substring(0, 4) == "http");

    // Runs every recovered validation, collecting legacy error strings in order.
    public static List<string> Validate(AccountInput a, bool nameTaken)
    {
        var errors = new List<string>();
        if (nameTaken)
            errors.Add("An account with that name already exists.");
        // Legacy APEX page item P3_CUSTOMER_TERRITORY_ID is required (Value Required).
        if (string.IsNullOrEmpty(a.CustomerTerritoryId))
            errors.Add("Territory must have some value.");
        if (!string.IsNullOrEmpty(a.Tags) && InvalidTagChars.IsMatch(a.Tags))
            errors.Add(@"Tags may not contain the following characters: : ; \ / ? &");
        if (!StartsWithHttp(a.CustomerWebSite))
            errors.Add("Please provide a URL that begins with, \"http\".");
        if (!StartsWithHttp(a.CustomerLinkedin))
            errors.Add("Please provide a URL that begins with, \"http\".");
        if (!StartsWithHttp(a.CustomerFacebook))
            errors.Add("Please provide a URL that begins with, \"http\".");
        if (!StartsWithHttp(a.CustomerTwitter))
            errors.Add("Please provide a URL that begins with, \"http\".");
        return errors;
    }

    public async Task<IEnumerable<Account>> ListAsync(string? search)
    {
        using var conn = _factory.Create();
        var sql = $"SELECT {COLS} FROM {TABLE}";
        object? p = null;
        if (!string.IsNullOrWhiteSpace(search))
        {
            sql += " WHERE UPPER(customer_name) LIKE UPPER(:s) OR UPPER(tags) LIKE UPPER(:s)";
            p = new { s = "%" + search + "%" };
        }
        sql += " ORDER BY customer_name";
        return await conn.QueryAsync<Account>(sql, p);
    }

    public async Task<IEnumerable<Territory>> ListTerritoriesAsync()
    {
        using var conn = _factory.Create();
        return await conn.QueryAsync<Territory>(
            "SELECT TO_CHAR(id) AS Id, territory_name AS Name " +
            "FROM apex_sample.eba_sales_territories ORDER BY territory_name");
    }

    public async Task<Account?> GetAsync(string id)
    {
        using var conn = _factory.Create();
        return await conn.QueryFirstOrDefaultAsync<Account>(
            $"SELECT {COLS} FROM {TABLE} WHERE TO_CHAR(id) = :id", new { id });
    }

    // Mirrors NOT_EXISTS: upper(customer_name)=upper(:name) excluding self.
    public async Task<bool> IsNameTakenAsync(string customerName, string? excludeId)
    {
        using var conn = _factory.Create();
        var count = await conn.ExecuteScalarAsync<int>(
            $@"SELECT COUNT(*) FROM {TABLE}
                WHERE (:pid IS NULL OR :pid != TO_CHAR(id))
                  AND UPPER(customer_name) = UPPER(:pname)",
            new { pid = excludeId, pname = customerName });
        return count > 0;
    }

    public async Task<AccountSaveResult> CreateAsync(AccountInput input)
    {
        var taken = !string.IsNullOrEmpty(input.CustomerName)
                    && await IsNameTakenAsync(input.CustomerName!, null);
        var errors = Validate(input, taken);
        if (errors.Count > 0) return new AccountSaveResult(false, null, errors);

        using var conn = _factory.Create();
        // RETURNING the id as TEXT into a varchar out param — the raw NUMBER
        // overflows Int64/decimal (39-digit EBA key), so never bind it numerically.
        var p = new DynamicParameters();
        p.Add("CustomerName", input.CustomerName);
        p.Add("Tags", input.Tags);
        p.Add("CustomerWebSite", input.CustomerWebSite);
        p.Add("CustomerLinkedin", input.CustomerLinkedin);
        p.Add("CustomerFacebook", input.CustomerFacebook);
        p.Add("CustomerTwitter", input.CustomerTwitter);
        p.Add("CustomerTerritoryId", input.CustomerTerritoryId);
        p.Add("NewId", dbType: DbType.String, direction: ParameterDirection.Output, size: 64);
        await conn.ExecuteAsync(
            $@"INSERT INTO {TABLE}
                   (customer_name, tags, customer_web_site, customer_linkedin,
                    customer_facebook, customer_twitter, customer_territory_id,
                    customer_is_key_account_yn)
               VALUES (:CustomerName, :Tags, :CustomerWebSite, :CustomerLinkedin,
                    :CustomerFacebook, :CustomerTwitter, :CustomerTerritoryId, 'N')
               RETURNING TO_CHAR(id) INTO :NewId",
            p);
        return new AccountSaveResult(true, p.Get<string>("NewId"), errors);
    }

    public async Task<AccountSaveResult> UpdateAsync(string id, AccountInput input)
    {
        var taken = !string.IsNullOrEmpty(input.CustomerName)
                    && await IsNameTakenAsync(input.CustomerName!, id);
        var errors = Validate(input, taken);
        if (errors.Count > 0) return new AccountSaveResult(false, id, errors);

        using var conn = _factory.Create();
        await conn.ExecuteAsync(
            $@"UPDATE {TABLE}
                  SET customer_name = :CustomerName, tags = :Tags,
                      customer_web_site = :CustomerWebSite,
                      customer_linkedin = :CustomerLinkedin,
                      customer_facebook = :CustomerFacebook,
                      customer_twitter = :CustomerTwitter,
                      customer_territory_id = :CustomerTerritoryId
                WHERE TO_CHAR(id) = :Id",
            new { input.CustomerName, input.Tags, input.CustomerWebSite,
                  input.CustomerLinkedin, input.CustomerFacebook, input.CustomerTwitter,
                  input.CustomerTerritoryId, Id = id });
        return new AccountSaveResult(true, id, errors);
    }
}
