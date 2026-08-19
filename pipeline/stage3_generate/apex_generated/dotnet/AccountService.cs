using System;
using System.Collections.Generic;
using System.Data;
using System.Text.RegularExpressions;
using System.Threading.Tasks;
using Dapper;
using Oracle.ManagedDataAccess.Client;

namespace Sample.Apex.Accounts;

public sealed class AccountValidationException : Exception
{
    public IReadOnlyList<string> Errors { get; }

    public AccountValidationException(IReadOnlyList<string> errors)
        : base(errors is { Count: > 0 } ? errors[0] : "Validation failed.")
    {
        Errors = errors ?? Array.Empty<string>();
    }
}

public sealed class Account
{
    public long? Id { get; set; }
    public string? CustomerName { get; set; }
    public string? Tags { get; set; }
    public string? CustomerWebSite { get; set; }
    public string? CustomerLinkedIn { get; set; }
    public string? CustomerFacebook { get; set; }
    public string? CustomerTwitter { get; set; }
}

public interface IAccountService
{
    Task<long> CreateAsync(Account account);
    Task UpdateAsync(Account account);
    Task ValidateAsync(Account account);
}

public sealed class AccountService : IAccountService
{
    private readonly string _connectionString;

    // Mirrors APEX validation: Tags may not contain : ; \ / ? &
    // regexp_like( :P3_TAGS, '[:;#\/\\\?\&]' ) => invalid if any of these characters are present.
    private static readonly Regex InvalidTagChars =
        new(@"[:;#/\\?&]", RegexOptions.Compiled);

    public AccountService(string connectionString)
    {
        _connectionString = connectionString
            ?? throw new ArgumentNullException(nameof(connectionString));
    }

    private IDbConnection CreateConnection() => new OracleConnection(_connectionString);

    public async Task ValidateAsync(Account account)
    {
        if (account is null) throw new ArgumentNullException(nameof(account));

        var errors = new List<string>();

        // P3_CUSTOMER_NAME not duplicated (case-insensitive, excluding self)
        if (!string.IsNullOrEmpty(account.CustomerName))
        {
            if (await CustomerNameExistsAsync(account.CustomerName, account.Id))
            {
                errors.Add("An account with that name already exists.");
            }
        }

        // Valid Tag Characters
        if (!string.IsNullOrEmpty(account.Tags) && InvalidTagChars.IsMatch(account.Tags))
        {
            errors.Add(@"Tags may not contain the following characters: : ; \ / ? &");
        }

        // Website must start with http
        if (!StartsWithHttp(account.CustomerWebSite))
        {
            errors.Add("Please provide a URL that begins with, \"http\".");
        }

        // LinkedIn must start with http
        if (!StartsWithHttp(account.CustomerLinkedIn))
        {
            errors.Add("Please provide a URL that begins with, \"http\".");
        }

        // FB must start with http
        if (!StartsWithHttp(account.CustomerFacebook))
        {
            errors.Add("Please provide a URL that begins with, \"http\".");
        }

        // Twitter must start with http
        if (!StartsWithHttp(account.CustomerTwitter))
        {
            errors.Add("Please provide a URL that begins with, \"http\".");
        }

        if (errors.Count > 0)
        {
            throw new AccountValidationException(errors);
        }
    }

    // APEX: substr(:P3_X, 1, 4) = 'http'
    // In APEX these validations only fire when the item has a value; empty/null passes.
    private static bool StartsWithHttp(string? value)
    {
        if (string.IsNullOrEmpty(value)) return true;
        return value.Length >= 4 && value.Substring(0, 4) == "http";
    }

    private async Task<bool> CustomerNameExistsAsync(string customerName, long? excludeId)
    {
        const string sql = @"
select count(*)
  from eba_sales_customers
 where (:p_id is null or :p_id != id)
   and upper(customer_name) = upper(:p_name)";

        using var conn = CreateConnection();
        var count = await conn.ExecuteScalarAsync<int>(sql, new
        {
            p_id = excludeId,
            p_name = customerName
        });
        return count > 0;
    }

    public async Task<long> CreateAsync(Account account)
    {
        await ValidateAsync(account);

        const string sql = @"
insert into eba_sales_customers (
    customer_name,
    tags,
    customer_web_site,
    customer_linkedin,
    customer_facebook,
    customer_twitter
) values (
    :CustomerName,
    :Tags,
    :CustomerWebSite,
    :CustomerLinkedIn,
    :CustomerFacebook,
    :CustomerTwitter
)
returning id into :NewId";

        using var conn = CreateConnection();
        var p = new DynamicParameters();
        p.Add("CustomerName", account.CustomerName);
        p.Add("Tags", account.Tags);
        p.Add("CustomerWebSite", account.CustomerWebSite);
        p.Add("CustomerLinkedIn", account.CustomerLinkedIn);
        p.Add("CustomerFacebook", account.CustomerFacebook);
        p.Add("CustomerTwitter", account.CustomerTwitter);
        p.Add("NewId", dbType: DbType.Int64, direction: ParameterDirection.Output);

        await conn.ExecuteAsync(sql, p);

        var newId = p.Get<long>("NewId");
        account.Id = newId;
        return newId;
    }

    public async Task UpdateAsync(Account account)
    {
        if (account?.Id is null)
            throw new ArgumentException("Account Id is required for update.", nameof(account));

        await ValidateAsync(account);

        const string sql = @"
update eba_sales_customers
   set customer_name     = :CustomerName,
       tags              = :Tags,
       customer_web_site = :CustomerWebSite,
       customer_linkedin = :CustomerLinkedIn,
       customer_facebook = :CustomerFacebook,
       customer_twitter  = :CustomerTwitter
 where id = :Id";

        using var conn = CreateConnection();
        await conn.ExecuteAsync(sql, new
        {
            account.CustomerName,
            account.Tags,
            account.CustomerWebSite,
            account.CustomerLinkedIn,
            account.CustomerFacebook,
            account.CustomerTwitter,
            account.Id
        });
    }
}