using Microsoft.AspNetCore.Mvc;
using ModernApi.Models;
using ModernApi.Services;

namespace ModernApi.Controllers;

// Modern "after" of the APEX Opportunities CRM Account Details page.
// Endpoints mirror the generated OpenAPI contract (accounts.yaml). Business
// validations live in AccountService and preserve the recovered APEX rules.
[ApiController]
[Route("api/accounts")]
public sealed class AccountsController : ControllerBase
{
    private readonly IAccountService _svc;
    public AccountsController(IAccountService svc) => _svc = svc;

    [HttpGet]
    public async Task<IActionResult> List([FromQuery] string? search)
        => Ok(await _svc.ListAsync(search));

    [HttpGet("territories")]
    public async Task<IActionResult> Territories()
        => Ok(await _svc.ListTerritoriesAsync());

    [HttpGet("{id}")]
    public async Task<IActionResult> Get(string id)
    {
        var a = await _svc.GetAsync(id);
        return a is null ? NotFound() : Ok(a);
    }

    // Replicates the APEX NOT_EXISTS validation on P3_CUSTOMER_NAME.
    [HttpGet("validate-name")]
    public async Task<IActionResult> ValidateName([FromQuery] string customerName,
                                                  [FromQuery] string? excludeId)
    {
        var taken = await _svc.IsNameTakenAsync(customerName, excludeId);
        return Ok(new { available = !taken,
                        message = taken ? "An account with that name already exists." : null });
    }

    [HttpPost]
    public async Task<IActionResult> Create([FromBody] AccountInput input)
    {
        var r = await _svc.CreateAsync(input);
        if (!r.Ok) return BadRequest(new { code = "VALIDATION_ERROR", errors = r.Errors });
        return Created($"/api/accounts/{r.Id}", new { id = r.Id });
    }

    [HttpPut("{id}")]
    public async Task<IActionResult> Update(string id, [FromBody] AccountInput input)
    {
        var r = await _svc.UpdateAsync(id, input);
        if (!r.Ok) return BadRequest(new { code = "VALIDATION_ERROR", errors = r.Errors });
        return Ok(new { id });
    }
}
