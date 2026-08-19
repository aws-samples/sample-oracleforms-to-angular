using Microsoft.AspNetCore.Mvc;
using ModernApi.Services;

namespace ModernApi.Controllers;

// Generic reports endpoint. The migration pipeline registers each converted
// Oracle Interactive Report here; this controller serves them all unchanged.
[ApiController]
[Route("api/reports")]
public sealed class ReportsController : ControllerBase
{
    private readonly IReportService _svc;
    public ReportsController(IReportService svc) => _svc = svc;

    [HttpGet]
    public async Task<IActionResult> List() => Ok(await _svc.ListReportsAsync());

    [HttpGet("{key}")]
    public async Task<IActionResult> Run(string key,
        [FromQuery] string? sort, [FromQuery] string? dir)
    {
        var data = await _svc.RunReportAsync(key, sort, dir);
        return data is null ? NotFound() : Ok(data);
    }
}
