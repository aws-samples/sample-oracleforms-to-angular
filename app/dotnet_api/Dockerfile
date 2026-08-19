# Oracle modernization sample — .NET 8 Web API — multi-stage build for linux/amd64 (Fargate).
# Build the image and push to your ECR repository, then deploy via the infrastructure stack.
FROM mcr.microsoft.com/dotnet/sdk:8.0 AS build
WORKDIR /src
COPY ModernApi.csproj ./
RUN dotnet restore ModernApi.csproj
COPY . ./
RUN dotnet publish ModernApi.csproj -c Release -o /app --no-restore

FROM mcr.microsoft.com/dotnet/aspnet:8.0 AS runtime
WORKDIR /app
COPY --from=build /app ./
# ASP.NET Core listens on 8080; the ALB target group / health check use this port.
ENV ASPNETCORE_URLS=http://+:8080
EXPOSE 8080
ENTRYPOINT ["dotnet", "ModernApi.dll"]
