using System;
using System.Diagnostics;
using System.Drawing;
using System.Globalization;
using System.IO;
using System.Reflection;
using System.Security.AccessControl;
using System.Security.Cryptography;
using System.Security.Principal;
using System.Text;
using System.Text.RegularExpressions;
using System.Threading.Tasks;
using System.Windows.Forms;
using System.Collections.Generic;
using System.Web.Script.Serialization;
using System.Net;

[assembly: AssemblyTitle("Security Presence 설치")]
[assembly: AssemblyDescription("Windows PC 상태, IP 정보 및 전원 관리 에이전트 설치 및 제거")]
[assembly: AssemblyCompany("Security Presence")]
[assembly: AssemblyProduct("Security Presence Agent")]
[assembly: AssemblyVersion("0.5.0.0")]
[assembly: AssemblyFileVersion("0.5.0.0")]

namespace SecurityPresence
{
    internal static class Program
    {
        internal const string PayloadResource = "SecurityPresence.Install.ps1";
        internal const string DisplayResource = "SecurityPresence.Display.txt";
        internal static readonly string InstallRoot = Path.Combine(
            Environment.GetFolderPath(Environment.SpecialFolder.CommonApplicationData), "SecurityPresenceAgent");
        internal static readonly string StagingRoot = Path.Combine(
            Environment.GetFolderPath(Environment.SpecialFolder.CommonApplicationData), "SecurityPresenceInstaller");
        internal static readonly string ExecutablePath = Path.GetFullPath(Assembly.GetExecutingAssembly().Location);

        [STAThread]
        private static int Main(string[] args)
        {
            Application.EnableVisualStyles();
            Application.SetCompatibleTextRenderingDefault(false);
            try
            {
                if (args.Length == 1 && args[0] == "--validate-payload")
                {
                    try
                    {
                        byte[] bytes = ReadResource(PayloadResource);
                        string text = Encoding.UTF8.GetString(bytes);
                        if (bytes.Length <= 100 || !text.Contains("SetupExecutablePath") ||
                            text.Contains("__CONFIG_BASE64__") || text.Contains("__AGENT_BASE64__") ||
                            text.Contains("__UNINSTALL_BASE64__") || text.Contains("__SERVICE_BASE64__")) return 2;
                        ReadEmbeddedConfiguration();
                        return 0;
                    }
                    catch { return 2; }
                }
                bool uninstall = args.Length == 1 && args[0] == "--uninstall";
                bool statusOnly = args.Length == 1 && args[0] == "--status";
                bool helper = args.Length == 3 && args[0] == "--uninstall-helper";
                if (args.Length != 0 && !uninstall && !helper && !statusOnly)
                    throw new InvalidOperationException("지원하지 않는 실행 옵션입니다.");
                int parentPid = 0;
                long parentTicks = 0;
                if (helper)
                {
                    if (!Int32.TryParse(args[1], NumberStyles.None, CultureInfo.InvariantCulture, out parentPid)
                        || !Int64.TryParse(args[2], NumberStyles.None, CultureInfo.InvariantCulture, out parentTicks)
                        || parentPid <= 0 || parentTicks <= 0)
                        throw new InvalidOperationException("제거 작업 정보를 확인할 수 없습니다.");
                    SafeFiles.ValidateHelperPath(ExecutablePath);
                    uninstall = true;
                }
                using (SetupForm form = new SetupForm(uninstall, helper, parentPid, parentTicks, statusOnly))
                {
                    Application.Run(form);
                    return form.ResultExitCode;
                }
            }
            catch (Exception)
            {
                MessageBox.Show("설치 프로그램을 시작하지 못했습니다.\n관리자 권한 및 설치 파일을 확인해 주세요.",
                    "Security Presence", MessageBoxButtons.OK, MessageBoxIcon.Error);
                return 1;
            }
        }

        internal static byte[] ReadResource(string name)
        {
            using (Stream input = Assembly.GetExecutingAssembly().GetManifestResourceStream(name))
            {
                if (input != null)
                {
                    using (MemoryStream output = new MemoryStream())
                    {
                        input.CopyTo(output);
                        return output.ToArray();
                    }
                }
            }
            if (name != PayloadResource && name != DisplayResource)
                throw new InvalidOperationException("알 수 없는 설치 구성 파일입니다.");
            // Build a generic executable first; the server appends the device-specific
            // payload in memory, so enrollment credentials never enter compiler staging.
            const int footerSize = 48;
            using (FileStream file = new FileStream(ExecutablePath, FileMode.Open, FileAccess.Read, FileShare.Read))
            using (BinaryReader reader = new BinaryReader(file, Encoding.UTF8))
            {
                if (file.Length <= footerSize) throw new InvalidDataException("설치 구성 파일이 없습니다.");
                file.Seek(-footerSize, SeekOrigin.End);
                byte[] expectedHash = ReadExactly(reader, 32);
                uint scriptLength = reader.ReadUInt32();
                uint displayLength = reader.ReadUInt32();
                byte[] magic = ReadExactly(reader, 8);
                if (Encoding.ASCII.GetString(magic) != "SPSETUP1"
                    || scriptLength < 100 || scriptLength > 4 * 1024 * 1024
                    || displayLength < 1 || displayLength > 4096)
                    throw new InvalidDataException("설치 구성 파일이 손상되었습니다.");
                long payloadLength = (long)scriptLength + displayLength;
                if (payloadLength + footerSize >= file.Length)
                    throw new InvalidDataException("설치 구성 파일의 크기가 올바르지 않습니다.");
                file.Seek(-(footerSize + payloadLength), SeekOrigin.End);
                byte[] combined = ReadExactly(reader, checked((int)payloadLength));
                byte[] actualHash;
                using (SHA256 sha = SHA256.Create()) actualHash = sha.ComputeHash(combined);
                int difference = 0;
                for (int i = 0; i < expectedHash.Length; i++) difference |= expectedHash[i] ^ actualHash[i];
                if (difference != 0) throw new InvalidDataException("설치 구성 파일 검증에 실패했습니다.");
                int offset = name == PayloadResource ? 0 : (int)scriptLength;
                int length = name == PayloadResource ? (int)scriptLength : (int)displayLength;
                byte[] result = new byte[length];
                Buffer.BlockCopy(combined, offset, result, 0, length);
                return result;
            }
        }

        private static byte[] ReadExactly(BinaryReader reader, int length)
        {
            byte[] bytes = reader.ReadBytes(length);
            if (bytes.Length != length) throw new EndOfStreamException("설치 구성 파일이 완전하지 않습니다.");
            return bytes;
        }

        internal static Dictionary<string, object> ReadEmbeddedConfiguration()
        {
            string script = Encoding.UTF8.GetString(ReadResource(PayloadResource));
            Match match = Regex.Match(script,
                @"(?m)^\s*\$configBytes\s*=\s*\[Convert\]::FromBase64String\('([A-Za-z0-9+/=]+)'\)\s*$");
            if (!match.Success || match.Groups[1].Value.Length > 24000)
                throw new SetupConnectionException("configuration_invalid");
            byte[] bytes = Convert.FromBase64String(match.Groups[1].Value);
            if (bytes.Length > 16384) throw new SetupConnectionException("configuration_invalid");
            Dictionary<string, object> config = new JavaScriptSerializer { MaxJsonLength = 16384, RecursionLimit = 12 }
                .Deserialize<Dictionary<string, object>>(Encoding.UTF8.GetString(bytes));
            ConnectionDiagnostics.ValidateInstallerConfiguration(config);
            return config;
        }

        internal static string QuoteArgument(string value)
        {
            StringBuilder result = new StringBuilder("\"");
            int slashes = 0;
            foreach (char c in value)
            {
                if (c == '\\') { slashes++; continue; }
                if (c == '"') result.Append('\\', slashes * 2 + 1);
                else result.Append('\\', slashes);
                result.Append(c);
                slashes = 0;
            }
            result.Append('\\', slashes * 2).Append('"');
            return result.ToString();
        }

        internal static string PowerShellPath
        {
            get
            {
                return Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.Windows),
                    "System32", "WindowsPowerShell", "v1.0", "powershell.exe");
            }
        }

        internal static ProcessStartInfo HiddenProcess(string executable, string arguments)
        {
            ProcessStartInfo info = new ProcessStartInfo(executable, arguments)
            {
                UseShellExecute = false,
                CreateNoWindow = true,
                WindowStyle = ProcessWindowStyle.Hidden,
                WorkingDirectory = Path.GetDirectoryName(executable)
            };
            if (String.Equals(executable, PowerShellPath, StringComparison.OrdinalIgnoreCase))
            {
                // The launcher may be started from PowerShell 7. Windows PowerShell 5.1
                // must load its own trusted machine modules instead of inherited PS7 modules.
                info.EnvironmentVariables["PSModulePath"] =
                    Path.Combine(Path.GetDirectoryName(PowerShellPath), "Modules") + ";" +
                    Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.ProgramFiles), "WindowsPowerShell", "Modules");
            }
            return info;
        }

        internal static int RunScript(string path, string extraArguments, string standardInput = null, Action<string> phaseReceived = null)
        {
            SafeFiles.AssertNoReparse(path);
            ProcessStartInfo info = HiddenProcess(PowerShellPath,
                "-NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -File " + QuoteArgument(path) + extraArguments);
            info.RedirectStandardOutput = true;
            info.RedirectStandardError = true;
            info.RedirectStandardInput = standardInput != null;
            using (Process process = new Process())
            {
                process.StartInfo = info;
                // Deliberately discard script output: embedded enrollment credentials must never
                // appear in the UI, diagnostics or a copied terminal transcript.
                process.OutputDataReceived += delegate(object sender, DataReceivedEventArgs output)
                {
                    if (phaseReceived != null && output.Data != null &&
                        Regex.IsMatch(output.Data, "^SECURITY_PRESENCE_PHASE:(validate_configuration|server_preflight|validate_existing|protect_files|stop_previous|preserve_configuration|write_files|configure_service|register_application|create_status_shortcut|start_service|start_service_uncertain|rollback_failed)$"))
                        phaseReceived(output.Data.Substring("SECURITY_PRESENCE_PHASE:".Length));
                };
                process.ErrorDataReceived += delegate { };
                process.Start();
                process.BeginOutputReadLine();
                process.BeginErrorReadLine();
                if (standardInput != null)
                {
                    process.StandardInput.WriteLine(standardInput);
                    process.StandardInput.Close();
                }
                if (!process.WaitForExit(300000))
                {
                    try { process.Kill(); process.WaitForExit(10000); } catch { }
                    return 124;
                }
                process.WaitForExit();
                return process.ExitCode;
            }
        }
    }

    internal sealed class SetupConnectionException : Exception
    {
        internal readonly string Code;
        internal SetupConnectionException(string code) : base(code) { Code = code; }
    }

    internal sealed class ConnectionCheck
    {
        internal bool Connected;
        internal string Code;
        internal DateTime? LastSuccessUtc;
        internal DateTime? UpdatedUtc;
        internal bool NeedsAdmin;
        internal int? HttpStatus;
    }

    internal static class ConnectionDiagnostics
    {
        internal static string Text(Dictionary<string, object> config, string key)
        {
            object value;
            return config != null && config.TryGetValue(key, out value) && value is string ? (string)value : "";
        }

        internal static bool IsIntegratedPrefix(string prefix)
        {
            return prefix == "/api/v1/agent" || prefix == "/manage/it/api/v1/agent";
        }

        internal static Uri ValidateEndpoint(Dictionary<string, object> config)
        {
            if (config == null) throw new SetupConnectionException("configuration_invalid");
            string mode = Text(config, "deploymentMode");
            if (mode == "") mode = "production";
            Uri uri;
            if ((mode != "production" && mode != "development") ||
                !Uri.TryCreate(Text(config, "serverUrl"), UriKind.Absolute, out uri) ||
                uri.AbsolutePath != "/" || uri.UserInfo != "" || uri.Query != "" || uri.Fragment != "")
                throw new SetupConnectionException("configuration_invalid");
            string host = uri.DnsSafeHost.TrimEnd('.').ToLowerInvariant();
            bool local = uri.IsLoopback || host == "localhost" || host.EndsWith(".localhost", StringComparison.Ordinal);
            IPAddress address;
            if (IPAddress.TryParse(host.Trim('[', ']'), out address))
            {
                if (address.IsIPv4MappedToIPv6) address = address.MapToIPv4();
                local = local || IPAddress.IsLoopback(address) || address.Equals(IPAddress.Any) || address.Equals(IPAddress.IPv6Any);
            }
            if ((mode == "production" && (uri.Scheme != "https" || local)) ||
                (uri.Scheme != "https" && !(mode == "development" && uri.Scheme == "http" && uri.IsLoopback)))
                throw new SetupConnectionException("production_endpoint_invalid");
            string prefix = Text(config, "apiPrefix");
            if (!IsIntegratedPrefix(prefix) && !(mode == "development" && prefix == "/api"))
                throw new SetupConnectionException("configuration_invalid");
            if (!Regex.IsMatch(Text(config, "expectedServerId"), "^[a-f0-9]{64}$"))
                throw new SetupConnectionException("server_identity_missing");
            return uri;
        }

        internal static void ValidateInstallerConfiguration(Dictionary<string, object> config)
        {
            ValidateEndpoint(config);
            object interval;
            int seconds;
            if (!config.TryGetValue("heartbeatIntervalSeconds", out interval) ||
                !Int32.TryParse(Convert.ToString(interval, CultureInfo.InvariantCulture), out seconds) || seconds != 15)
                throw new SetupConnectionException("configuration_invalid");
            Guid identifier;
            bool hasIdentity = Guid.TryParseExact(Text(config, "deviceId"), "D", out identifier) && identifier != Guid.Empty;
            bool hasToken = Regex.IsMatch(Text(config, "deviceToken"), "^[A-Za-z0-9_-]{32,256}$");
            bool hasEnrollment = Regex.IsMatch(Text(config, "enrollmentToken"), "^[A-Za-z0-9_-]{24,256}$");
            bool automatic = Text(config, "registrationMode") == "automatic" &&
                IsIntegratedPrefix(Text(config, "apiPrefix")) &&
                Guid.TryParseExact(Text(config, "ticketId"), "D", out identifier) && identifier != Guid.Empty &&
                Regex.IsMatch(Text(config, "registrationToken"), "^[A-Za-z0-9_-]{43}$") &&
                Text(config, "deviceId") == "" && Text(config, "deviceToken") == "" && Text(config, "enrollmentToken") == "";
            if (!automatic && (!hasIdentity || (!hasToken && !hasEnrollment)))
                throw new SetupConnectionException("configuration_invalid");
            if (Text(config, "registrationMode") == "automatic" &&
                (config.ContainsKey("ticketId") || config.ContainsKey("registrationToken")) && !automatic)
                throw new SetupConnectionException("configuration_invalid");
        }

        internal static bool IsReadyResponse(Dictionary<string, object> body, string expectedServerId)
        {
            object protocol, ready;
            Version version;
            return body != null && Text(body, "product") == "app-it-manager-agent" &&
                body.TryGetValue("protocol", out protocol) && protocol is int && (int)protocol == 1 &&
                body.TryGetValue("registrationReady", out ready) && ready is bool && (bool)ready &&
                Regex.IsMatch(expectedServerId ?? "", "^[a-f0-9]{64}$") && Text(body, "serverId") == expectedServerId &&
                Timestamp(body, "serverTime").HasValue &&
                Version.TryParse(Text(body, "latestAgentVersion"), out version) && version >= new Version(0, 5, 0);
        }

        internal static void CheckServerReadiness(Dictionary<string, object> config)
        {
            Uri server = ValidateEndpoint(config);
            ServicePointManager.SecurityProtocol |= SecurityProtocolType.Tls12;
            HttpWebRequest request = (HttpWebRequest)WebRequest.Create(server.AbsoluteUri.TrimEnd('/') + Text(config, "apiPrefix") + "/ready");
            request.Method = "GET";
            request.Accept = "application/json";
            request.AllowAutoRedirect = false;
            request.Timeout = 8000;
            request.ReadWriteTimeout = 8000;
            try
            {
                using (HttpWebResponse response = (HttpWebResponse)request.GetResponse())
                {
                    int status = (int)response.StatusCode;
                    if (status >= 300 && status < 400) throw new SetupConnectionException("ready_redirect");
                    if (status != 200 || response.ContentLength > 16384 ||
                        (response.ContentType ?? "").Split(';')[0].Trim().ToLowerInvariant() != "application/json")
                        throw new SetupConnectionException("ready_protocol");
                    using (Stream input = response.GetResponseStream())
                    using (MemoryStream buffer = new MemoryStream())
                    {
                        byte[] chunk = new byte[1024];
                        int count;
                        while ((count = input.Read(chunk, 0, chunk.Length)) > 0)
                        {
                            if (buffer.Length + count > 16384) throw new SetupConnectionException("ready_protocol");
                            buffer.Write(chunk, 0, count);
                        }
                        Dictionary<string, object> body;
                        try { body = new JavaScriptSerializer { MaxJsonLength = 16384, RecursionLimit = 8 }
                            .Deserialize<Dictionary<string, object>>(Encoding.UTF8.GetString(buffer.ToArray())); }
                        catch { throw new SetupConnectionException("ready_protocol"); }
                        if (body == null || Text(body, "product") != "app-it-manager-agent")
                            throw new SetupConnectionException("ready_protocol");
                        if (Text(body, "serverId") != "" && Text(body, "serverId") != Text(config, "expectedServerId"))
                            throw new SetupConnectionException("server_identity_mismatch");
                        object ready;
                        if (body.TryGetValue("registrationReady", out ready) && ready is bool && !(bool)ready)
                            throw new SetupConnectionException("ready_unavailable");
                        if (!IsReadyResponse(body, Text(config, "expectedServerId")))
                            throw new SetupConnectionException("ready_protocol");
                    }
                }
            }
            catch (WebException error)
            {
                string code = "ready_network";
                if (error.Status == WebExceptionStatus.NameResolutionFailure || error.Status == WebExceptionStatus.ProxyNameResolutionFailure) code = "ready_dns";
                else if (error.Status == WebExceptionStatus.TrustFailure || error.Status == WebExceptionStatus.SecureChannelFailure) code = "ready_tls";
                else if (error.Response != null)
                {
                    using (HttpWebResponse response = error.Response as HttpWebResponse)
                    {
                        int status = response == null ? 0 : (int)response.StatusCode;
                        code = status == 404 ? "ready_path" : status == 401 || status == 403 ? "ready_access_denied" : "ready_unavailable";
                    }
                }
                throw new SetupConnectionException(code);
            }
            finally { request.Abort(); }
        }

        internal static DateTime? Timestamp(Dictionary<string, object> value, string name)
        {
            string text = Text(value, name);
            DateTimeOffset timestamp;
            if (!Regex.IsMatch(text, @"(?:Z|[+-]\d{2}:\d{2})$") ||
                !DateTimeOffset.TryParse(text, CultureInfo.InvariantCulture, DateTimeStyles.None, out timestamp)) return null;
            return timestamp.UtcDateTime;
        }

        internal static ConnectionCheck EvaluateStatus(Dictionary<string, object> runtime,
            Dictionary<string, object> config, DateTime nowUtc, DateTime minimumSuccessUtc)
        {
            ConnectionCheck result = new ConnectionCheck { Code = "status_invalid" };
            object version, admin, http;
            if (runtime == null || !runtime.TryGetValue("version", out version) || !(version is int) || (int)version != 1) return result;
            string code = Text(runtime, "code");
            if (!Regex.IsMatch(code, "^(starting|configuration_invalid|registration_pending|registration_network_error|registration_blocked|registration_save_failed|heartbeat_network_error|authentication_failed|heartbeat_connected)$")) return result;
            result.LastSuccessUtc = Timestamp(runtime, "lastSuccessUtc");
            result.UpdatedUtc = Timestamp(runtime, "updatedUtc");
            if (!runtime.TryGetValue("needsAdmin", out admin) || !(admin is bool)) return result;
            result.NeedsAdmin = (bool)admin;
            if (runtime.TryGetValue("httpStatus", out http) && http is int && (int)http >= 100 && (int)http <= 599) result.HttpStatus = (int)http;
            if (!result.UpdatedUtc.HasValue || (nowUtc - result.UpdatedUtc.Value).TotalSeconds < -5 ||
                (nowUtc - result.UpdatedUtc.Value).TotalSeconds > 45)
            { result.Code = "status_stale"; return result; }
            // Invalid configuration deliberately omits unsafe raw endpoint fields.
            if (code == "configuration_invalid") { result.Code = code; return result; }
            try { ValidateEndpoint(config); }
            catch (SetupConnectionException error) { result.Code = error.Code; result.NeedsAdmin = true; return result; }
            Uri expected, actual;
            string configuredId = Text(config, "deviceId"), reportedId = Text(runtime, "deviceId");
            Guid expectedId, actualId;
            bool sameIdentity = configuredId == "" && reportedId == "";
            if (!sameIdentity)
                sameIdentity = Guid.TryParseExact(configuredId, "D", out expectedId) && expectedId != Guid.Empty &&
                    Guid.TryParseExact(reportedId, "D", out actualId) && actualId == expectedId;
            bool contextMatches = Uri.TryCreate(Text(config, "serverUrl"), UriKind.Absolute, out expected) &&
                Uri.TryCreate(Text(runtime, "serverUrl"), UriKind.Absolute, out actual) &&
                expected.AbsoluteUri.TrimEnd('/') == actual.AbsoluteUri.TrimEnd('/') &&
                Text(config, "apiPrefix") == Text(runtime, "apiPrefix") &&
                sameIdentity;
            if (Text(runtime, "expectedServerId") != Text(config, "expectedServerId")) contextMatches = false;
            if (!contextMatches) { result.Code = "status_context_changed"; return result; }
            result.Code = code;
            if (code == "heartbeat_connected" && Text(runtime, "phase") == "heartbeat" && !result.NeedsAdmin && result.LastSuccessUtc.HasValue &&
                result.LastSuccessUtc.Value >= minimumSuccessUtc &&
                (nowUtc - result.LastSuccessUtc.Value).TotalSeconds >= -5 &&
                (nowUtc - result.LastSuccessUtc.Value).TotalSeconds <= 45 &&
                result.LastSuccessUtc.Value <= result.UpdatedUtc.Value.AddSeconds(5))
                result.Connected = true;
            else if (code == "heartbeat_connected") result.Code = "heartbeat_not_fresh";
            return result;
        }

        internal static string Explain(string code)
        {
            switch (code)
            {
                case "production_endpoint_invalid": return "운영 설치 파일의 서버 주소가 HTTPS 운영 주소가 아닙니다. 관리자에게 운영 서버에서 발급한 새 설치 파일을 요청하세요.";
                case "server_identity_missing": return "설치 파일에 서버 식별 정보가 없습니다. 운영 서버에서 새 설치 파일을 발급받아 주세요.";
                case "server_identity_mismatch": return "설치 파일을 발급한 서버와 연결 대상 서버가 다릅니다. 현재 파일로는 설치할 수 없습니다.";
                case "ready_dns": return "서버 이름을 찾을 수 없습니다. 인터넷·사내 DNS·VPN 연결과 서버 주소를 확인하세요.";
                case "ready_tls": return "HTTPS 인증서를 확인하지 못했습니다. PC 날짜와 서버 인증서를 확인하세요. 인증서 검증을 끄지 마세요.";
                case "ready_path": return "서버에서 에이전트 연결 경로를 찾지 못했습니다. 운영 서버의 배포 경로를 관리자에게 확인해 주세요.";
                case "ready_redirect": return "서버가 로그인 또는 다른 주소로 이동을 요구합니다. 에이전트 API의 직접 연결 경로를 확인해 주세요.";
                case "ready_access_denied": return "서버 또는 프록시가 연결 준비 확인을 차단했습니다. 에이전트 API 접근 설정을 확인하세요.";
                case "ready_unavailable": return "서버가 등록 준비를 완료하지 못했습니다. 서버 상태를 복구한 뒤 다시 시도하세요.";
                case "ready_protocol": return "응답이 지원되는 에이전트 서버 형식과 일치하지 않습니다. 서버 배포와 설치 파일 버전을 확인하세요.";
                case "ready_network": return "서버에 연결하지 못했거나 응답 시간이 초과됐습니다. 네트워크·방화벽·VPN을 확인하고 다시 시도하세요.";
                case "configuration_invalid": return "연결 설정이 올바르지 않습니다. 관리자에게 이 PC에 맞는 최신 설치 파일을 요청하세요.";
                case "registration_blocked": return "서버가 등록을 거부했습니다. 등록 티켓 만료, 기존 PC 연결 또는 하드웨어 식별 충돌을 관리자에게 확인해 주세요.";
                case "authentication_failed": return "서버가 이 PC의 인증을 거부했습니다. 관리자에게 등록 상태 확인과 복구 설치 파일을 요청하세요.";
                case "registration_save_failed": return "서버 응답을 받았지만 등록 정보를 안전하게 저장하지 못했습니다. 설치 폴더 권한과 디스크 상태를 확인하세요.";
                case "registration_network_error": return "PC 등록 중 서버 연결에 실패했습니다. 네트워크가 복구되면 에이전트가 재시도합니다.";
                case "heartbeat_network_error": return "최근 상태 전송에 실패했습니다. 서버·네트워크 연결을 확인하세요. 이전 연결 성공은 현재 연결을 보장하지 않습니다.";
                case "status_stale": return "연결 상태 기록이 갱신되지 않습니다. 서비스가 중지됐거나 에이전트가 실행되지 않을 수 있습니다. 진단 로그와 Windows 서비스 상태를 확인하세요.";
                case "status_missing": return "현재 연결 상태 기록이 없습니다. 서비스 시작 여부를 확인하고, 계속 발생하면 최신 설치 파일로 복구하세요.";
                case "status_invalid": return "연결 상태 기록을 읽거나 검증하지 못했습니다. 설치 폴더 권한과 진단 로그를 확인하세요.";
                case "status_context_changed": return "현재 설정과 상태 기록이 일치하지 않습니다. 새 설정의 상태 전송을 기다리거나 관리자에게 복구를 요청하세요.";
                case "registration_pending": return "서버 등록을 진행하고 있습니다. 아직 등록·연결 성공을 확인하지 못했습니다.";
                case "starting": return "에이전트가 시작 중입니다. 아직 인증된 상태 전송을 확인하지 못했습니다.";
                case "heartbeat_not_fresh": return "이번 확인에 사용할 수 있는 새 상태 전송 성공 기록이 없습니다. 현재 연결을 다시 확인해 주세요.";
                default: return "연결을 확인하지 못했습니다. 표시된 상태 코드를 관리자에게 전달하고 진단 로그를 확인하세요.";
            }
        }
    }

    internal static class SafeFiles
    {
        private static readonly SecurityIdentifier SystemSid = new SecurityIdentifier(WellKnownSidType.LocalSystemSid, null);
        private static readonly SecurityIdentifier AdminSid = new SecurityIdentifier(WellKnownSidType.BuiltinAdministratorsSid, null);

        internal static void AssertNoReparse(string path)
        {
            string fullPath = Path.GetFullPath(path);
            string current = fullPath;
            while (!String.IsNullOrEmpty(current))
            {
                if (File.Exists(current) || Directory.Exists(current))
                {
                    if ((File.GetAttributes(current) & FileAttributes.ReparsePoint) != 0)
                        throw new InvalidOperationException("연결된 폴더 또는 파일에는 설치할 수 없습니다.");
                }
                string parent = Path.GetDirectoryName(current);
                if (String.Equals(parent, current, StringComparison.OrdinalIgnoreCase)) break;
                current = parent;
            }
        }

        private static bool TrustedIdentity(IdentityReference identity)
        {
            SecurityIdentifier sid = identity as SecurityIdentifier;
            return sid != null && (sid.Equals(SystemSid) || sid.Equals(AdminSid));
        }

        internal static void AssertPrivate(string path, bool directory)
        {
            AssertNoReparse(path);
            FileSystemSecurity security = directory
                ? (FileSystemSecurity)Directory.GetAccessControl(path, AccessControlSections.Access | AccessControlSections.Owner)
                : (FileSystemSecurity)File.GetAccessControl(path, AccessControlSections.Access | AccessControlSections.Owner);
            if (!TrustedIdentity(security.GetOwner(typeof(SecurityIdentifier))))
                throw new InvalidOperationException("설치 폴더의 소유자를 확인할 수 없습니다.");
            foreach (FileSystemAccessRule rule in security.GetAccessRules(true, true, typeof(SecurityIdentifier)))
            {
                if (rule.AccessControlType == AccessControlType.Allow && !TrustedIdentity(rule.IdentityReference))
                    throw new InvalidOperationException("설치 폴더의 접근 권한이 안전하지 않습니다.");
            }
        }

        private static DirectorySecurity PrivateDirectorySecurity()
        {
            DirectorySecurity security = new DirectorySecurity();
            security.SetAccessRuleProtection(true, false);
            security.SetOwner(AdminSid);
            InheritanceFlags inheritance = InheritanceFlags.ContainerInherit | InheritanceFlags.ObjectInherit;
            security.AddAccessRule(new FileSystemAccessRule(AdminSid, FileSystemRights.FullControl,
                inheritance, PropagationFlags.None, AccessControlType.Allow));
            security.AddAccessRule(new FileSystemAccessRule(SystemSid, FileSystemRights.FullControl,
                inheritance, PropagationFlags.None, AccessControlType.Allow));
            return security;
        }

        internal static string NewStagingDirectory(string kind)
        {
            AssertNoReparse(Program.StagingRoot);
            if (!Directory.Exists(Program.StagingRoot))
                Directory.CreateDirectory(Program.StagingRoot, PrivateDirectorySecurity());
            AssertPrivate(Program.StagingRoot, true);
            string child = Path.Combine(Program.StagingRoot, kind + "-" + Guid.NewGuid().ToString("N"));
            if (Directory.Exists(child) || File.Exists(child)) throw new IOException("임시 폴더가 이미 존재합니다.");
            Directory.CreateDirectory(child, PrivateDirectorySecurity());
            AssertPrivate(child, true);
            return child;
        }

        internal static void WriteNewPrivateFile(string path, byte[] data)
        {
            AssertNoReparse(path);
            AssertPrivate(Path.GetDirectoryName(path), true);
            using (FileStream file = new FileStream(path, FileMode.CreateNew, FileAccess.Write, FileShare.None))
                file.Write(data, 0, data.Length);
            FileSecurity security = new FileSecurity();
            security.SetAccessRuleProtection(true, false);
            security.SetOwner(AdminSid);
            security.AddAccessRule(new FileSystemAccessRule(AdminSid, FileSystemRights.FullControl, AccessControlType.Allow));
            security.AddAccessRule(new FileSystemAccessRule(SystemSid, FileSystemRights.FullControl, AccessControlType.Allow));
            File.SetAccessControl(path, security);
            AssertPrivate(path, false);
        }

        internal static void ValidateInstalledAgent()
        {
            AssertPrivate(Program.InstallRoot, true);
            string marker = Path.Combine(Program.InstallRoot, ".security-presence-managed");
            AssertPrivate(marker, false);
            if (File.ReadAllText(marker).Trim() != "SecurityPresenceAgent/1")
                throw new InvalidOperationException("Security Presence 설치 정보를 확인할 수 없습니다.");
            AssertPrivate(Path.Combine(Program.InstallRoot, "uninstall.ps1"), false);
        }

        internal static void ValidateHelperPath(string path)
        {
            string directory = Path.GetDirectoryName(path);
            if (!String.Equals(Path.GetDirectoryName(directory), Program.StagingRoot, StringComparison.OrdinalIgnoreCase)
                || !Regex.IsMatch(Path.GetFileName(directory), "^uninstall-[a-f0-9]{32}$")
                || Path.GetFileName(path) != "SecurityPresenceSetup.exe")
                throw new InvalidOperationException("제거 도우미 경로가 올바르지 않습니다.");
            AssertPrivate(Program.StagingRoot, true);
            AssertPrivate(directory, true);
            AssertPrivate(path, false);
        }

        internal static void DeleteOwnInstallStage(string directory)
        {
            if (!String.Equals(Path.GetDirectoryName(directory), Program.StagingRoot, StringComparison.OrdinalIgnoreCase)
                || !Regex.IsMatch(Path.GetFileName(directory), "^install-[a-f0-9]{32}$")) return;
            try
            {
                AssertPrivate(Program.StagingRoot, true);
                AssertPrivate(directory, true);
                string script = Path.Combine(directory, "Install.ps1");
                if (File.Exists(script))
                {
                    AssertPrivate(script, false);
                    File.Delete(script);
                }
                Directory.Delete(directory, false);
            }
            catch { /* Never broaden cleanup to unknown files or directories. */ }
        }

        internal static void ScheduleHelperCleanup()
        {
            ValidateHelperPath(Program.ExecutablePath);
            string directory = Path.GetDirectoryName(Program.ExecutablePath);
            int pid = Process.GetCurrentProcess().Id;
            long ticks = Process.GetCurrentProcess().StartTime.ToUniversalTime().Ticks;
            // All literals originate from validated canonical paths, and are PowerShell single-quoted.
            // Cleanup waits for this exact process identity and deletes only two fixed paths.
            string script =
                "$ErrorActionPreference='Stop';" +
                "$p=Get-Process -Id " + pid.ToString(CultureInfo.InvariantCulture) + " -ErrorAction SilentlyContinue;" +
                "if($p -and $p.StartTime.ToUniversalTime().Ticks -eq " + ticks.ToString(CultureInfo.InvariantCulture) + "){$p.WaitForExit()};" +
                "$f='" + Program.ExecutablePath.Replace("'", "''") + "';" +
                "$d='" + directory.Replace("'", "''") + "';" +
                "$r='" + Program.StagingRoot.Replace("'", "''") + "';" +
                "foreach($v in @($r,$d,$f)){if(Test-Path -LiteralPath $v){" +
                "$i=Get-Item -LiteralPath $v -Force;if($i.Attributes -band [IO.FileAttributes]::ReparsePoint){exit 2};" +
                "$a=Get-Acl -LiteralPath $v;$s=@('S-1-5-18','S-1-5-32-544');" +
                "if($a.GetOwner([Security.Principal.SecurityIdentifier]).Value -notin $s){exit 3};" +
                "foreach($x in $a.GetAccessRules($true,$true,[Security.Principal.SecurityIdentifier])){" +
                "if($x.AccessControlType -eq 'Allow' -and $x.IdentityReference.Value -notin $s){exit 4}}}};" +
                "if(Test-Path -LiteralPath $f){[IO.File]::Delete($f)};" +
                "if(Test-Path -LiteralPath $d){[IO.Directory]::Delete($d,$false)}";
            string encoded = Convert.ToBase64String(Encoding.Unicode.GetBytes(script));
            Process.Start(Program.HiddenProcess(Program.PowerShellPath,
                "-NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -EncodedCommand " + encoded)).Dispose();
        }
    }

    internal sealed class SetupForm : Form
    {
        private readonly bool uninstall;
        private readonly bool helper;
        private readonly bool statusOnly;
        private readonly int parentPid;
        private readonly long parentTicks;
        private bool busy;
        private bool complete;
        private bool installed;
        private bool checking;
        internal int ResultExitCode = 1223;
        private int installationWarningCode;
        private string installPhase = "validate_configuration";
        private readonly System.Windows.Forms.Timer connectionTimer = new System.Windows.Forms.Timer();
        private Label title;
        private Label subtitle;
        private Label details;
        private Label status;
        private Label note;
        private ProgressBar progress;
        private Button primary;
        private Button cancel;
        private Button diagnostics;
        private string serverUrl;
        private string configuredEndpoint = "";
        private string deviceName;
        private bool localServer;
        internal SetupForm(bool uninstall, bool helper, int parentPid, long parentTicks)
            : this(uninstall, helper, parentPid, parentTicks, false) { }

        internal SetupForm(bool uninstall, bool helper, int parentPid, long parentTicks, bool statusOnly)
        {
            this.uninstall = uninstall;
            this.helper = helper;
            this.parentPid = parentPid;
            this.parentTicks = parentTicks;
            this.statusOnly = statusOnly;
            ReadDisplay();
            BuildWindow();
            if (helper) Shown += async delegate { await RunUninstallHelper(); };
            else if (statusOnly) Shown += async delegate { await VerifyConnection(false, DateTime.UtcNow.AddSeconds(-45)); };
            connectionTimer.Interval = 5000;
            connectionTimer.Tick += async delegate
            {
                if (!busy && !checking && !uninstall)
                    await VerifyConnection(false, DateTime.UtcNow.AddSeconds(-45));
            };
            FormClosing += delegate(object sender, FormClosingEventArgs e) { if (busy) e.Cancel = true; };
            FormClosed += delegate
            {
                connectionTimer.Stop();
                connectionTimer.Dispose();
                if (helper)
                {
                    try { SafeFiles.ScheduleHelperCleanup(); } catch { }
                }
            };
        }

        private void ReadDisplay()
        {
            serverUrl = "등록된 관리 서버";
            deviceName = "이 컴퓨터";
            try
            {
                string[] lines = Encoding.UTF8.GetString(Program.ReadResource(Program.DisplayResource))
                    .TrimStart('\uFEFF').Split(new[] { "\r\n", "\n" }, StringSplitOptions.None);
                Uri uri;
                if (lines.Length > 0 && Uri.TryCreate(lines[0], UriKind.Absolute, out uri)
                    && (uri.Scheme == "http" || uri.Scheme == "https")
                    && String.IsNullOrEmpty(uri.UserInfo) && String.IsNullOrEmpty(uri.Query))
                {
                    serverUrl = uri.GetLeftPart(UriPartial.Authority);
                    localServer = uri.IsLoopback;
                }
                if (lines.Length > 1 && !String.IsNullOrWhiteSpace(lines[1]))
                    deviceName = lines[1].Length > 100 ? lines[1].Substring(0, 100) : lines[1];
            }
            catch { }
        }

        private Label TextLabel(string text, int x, int y, int width, int height, float size, Color color, FontStyle style)
        {
            Label label = new Label();
            label.Text = text;
            label.SetBounds(x, y, width, height);
            label.Font = new Font("Malgun Gothic", size, style);
            label.ForeColor = color;
            label.AutoEllipsis = true;
            Controls.Add(label);
            return label;
        }

        private void BuildWindow()
        {
            Text = uninstall ? "Security Presence 제거" : statusOnly ? "App-IT-Manager 연결 상태" : "Security Presence 설치";
            ClientSize = new Size(700, 564);
            AutoScaleDimensions = new SizeF(96, 96);
            AutoScaleMode = AutoScaleMode.Dpi;
            FormBorderStyle = FormBorderStyle.FixedDialog;
            MaximizeBox = false;
            MinimizeBox = false;
            StartPosition = FormStartPosition.CenterScreen;
            BackColor = Color.FromArgb(248, 250, 252);
            Font = new Font("Malgun Gothic", 10);
            Icon = SystemIcons.Shield;

            Panel header = new Panel { BackColor = Color.FromArgb(17, 35, 52) };
            header.SetBounds(0, 0, 700, 96);
            Controls.Add(header);
            Label brand = new Label
            {
                Text = "SECURITY  PRESENCE",
                ForeColor = Color.White,
                Font = new Font("Segoe UI", 17, FontStyle.Bold),
                AutoSize = true,
                Location = new Point(32, 19)
            };
            header.Controls.Add(brand);
            Label tagline = new Label
            {
                Text = "Windows PC 연결 상태 모니터링",
                ForeColor = Color.FromArgb(171, 203, 220),
                Font = new Font("Malgun Gothic", 10),
                AutoSize = true,
                Location = new Point(34, 56)
            };
            header.Controls.Add(tagline);
            Color ink = Color.FromArgb(28, 45, 61);
            Color muted = Color.FromArgb(82, 98, 115);
            title = TextLabel(uninstall ? "이 PC에서 에이전트를 제거합니다" : "PC 상태 확인을 시작하세요", 32, 122, 636, 40, 20, ink, FontStyle.Bold);
            subtitle = TextLabel(uninstall ? "관리자 승인 후 Windows 서비스와 설치 파일을 삭제합니다." : "PC 상태·IP·MAC을 전송하고, 승인된 재부팅·종료 및 사내망 WOL 중계를 실행합니다.",
                34, 172, 632, 48, 10, muted, FontStyle.Regular);
            details = TextLabel(uninstall
                ? "제거 대상\r\nSecurity Presence Agent\r\n\r\n설치 위치\r\n" + Program.InstallRoot
                : "등록 이름    " + deviceName + "\r\n관리 서버    " + serverUrl + "\r\n설치 위치    " + Program.InstallRoot
                    + "\r\n\r\nWindows 서비스 자동 실행 · 일반 사용자는 중지·제거 불가\r\n자동 등록 시 하드웨어 UUID·BIOS 일련번호 확인\r\n등록된 통합 설치의 제거에는 관리자 승인 코드 필요",
                34, 229, 632, 146, 10, ink, FontStyle.Regular);
            status = TextLabel(uninstall ? "제거할 준비가 되었습니다." : "설치할 준비가 되었습니다.", 34, 384, 632, 28, 10, ink, FontStyle.Bold);
            progress = new ProgressBar { Style = ProgressBarStyle.Continuous };
            progress.SetBounds(34, 419, 632, 8);
            Controls.Add(progress);
            note = TextLabel(uninstall
                ? "대시보드의 등록 기록은 유지되며, 상태는 연결 끊김으로 바뀝니다."
                : (localServer
                    ? "로컬 주소는 명시적인 개발용 설정에서만 허용됩니다."
                    : "서버 준비 확인과 인증된 상태 전송을 통과해야 연결 성공으로 표시됩니다."),
                34, 441, 632, 37, 9, muted, FontStyle.Regular);

            cancel = new Button { Text = "취소", FlatStyle = FlatStyle.Flat, BackColor = Color.White, DialogResult = DialogResult.Cancel };
            cancel.FlatAppearance.BorderColor = Color.FromArgb(209, 218, 225);
            cancel.SetBounds(426, 500, 106, 38);
            cancel.Click += delegate { Close(); };
            Controls.Add(cancel);
            primary = new Button
            {
                Text = uninstall ? "제거" : statusOnly ? "다시 확인" : "설치",
                FlatStyle = FlatStyle.Flat,
                BackColor = Color.FromArgb(0, 113, 118),
                ForeColor = Color.White,
                Font = new Font("Malgun Gothic", 10, FontStyle.Bold)
            };
            primary.FlatAppearance.BorderSize = 0;
            primary.SetBounds(548, 500, 118, 38);
            primary.Click += async delegate
            {
                if (checking || busy) return;
                if (!uninstall && (installed || statusOnly))
                {
                    await VerifyConnection(true, DateTime.UtcNow);
                    return;
                }
                if (complete) { Close(); return; }
                if (uninstall) BeginUninstall();
                else await RunInstall();
            };
            Controls.Add(primary);
            diagnostics = new Button { Text = "진단 로그 보기", FlatStyle = FlatStyle.Flat, BackColor = Color.White, Visible = statusOnly };
            diagnostics.FlatAppearance.BorderColor = Color.FromArgb(209, 218, 225);
            diagnostics.SetBounds(34, 500, 146, 38);
            diagnostics.Click += delegate { OpenDiagnosticLog(); };
            Controls.Add(diagnostics);
            AcceptButton = primary;
            CancelButton = cancel;
            if (statusOnly)
            {
                title.Text = "현재 서버 연결을 확인합니다";
                subtitle.Text = "저장된 인증 정보만으로 연결 성공을 판단하지 않습니다.";
                details.Text = "이 PC: " + Environment.MachineName + "\r\n설치 위치: " + Program.InstallRoot;
                cancel.Text = "닫기";
            }
        }

        private void SetBusy(string text)
        {
            busy = true;
            primary.Enabled = false;
            cancel.Enabled = false;
            ControlBox = false;
            status.Text = text;
            progress.Style = ProgressBarStyle.Marquee;
            progress.MarqueeAnimationSpeed = 24;
            note.Text = "작업이 끝날 때까지 이 창을 유지해 주세요.";
        }

        private void Finish(int exitCode)
        {
            ResultExitCode = exitCode;
            busy = false;
            complete = true;
            ControlBox = true;
            primary.Enabled = true;
            primary.Text = "닫기";
            cancel.Visible = false;
            progress.Style = ProgressBarStyle.Continuous;
            progress.Value = exitCode == 0 || exitCode == 75 ? 100 : 0;
            if (exitCode == 75)
            {
                title.Text = "PC에서 에이전트 제거가 완료되었습니다";
                subtitle.Text = "서비스와 설치 파일은 제거했지만 서버의 완료 확인을 받지 못했습니다.";
                status.Text = "대시보드에는 제거 승인 상태가 남아 있을 수 있습니다.";
                note.Text = "관리자에게 이 PC의 실제 제거 완료 상태를 확인해 달라고 요청하세요.";
                return;
            }
            title.Text = exitCode == 0 ? "제거가 완료되었습니다" : "제거를 완료하지 못했습니다";
            subtitle.Text = exitCode == 0 ? "이 PC에서 상태 전송과 자동 실행을 중지했습니다." : "관리자 승인과 파일 사용 상태를 확인해 주세요.";
            status.Text = exitCode == 0 ? "Security Presence Agent가 제거되었습니다." : "작업 종료 코드: " + exitCode.ToString(CultureInfo.InvariantCulture);
            note.Text = exitCode == 0 ? "대시보드에는 마지막 연결 시각이 남아 있습니다."
                : "통합 설치는 관리자에게 새 제거 승인 코드를 요청한 뒤 다시 시도하세요.";
        }

        private static string ScriptFailureCode(int code)
        {
            switch (code)
            {
                case 21: return "ready_dns";
                case 22: return "ready_tls";
                case 23: return "ready_network";
                case 24: return "ready_unavailable";
                case 25: return "ready_path";
                case 26: return "ready_redirect";
                case 27: return "ready_protocol";
                case 28: return "ready_access_denied";
                case 29: return "server_identity_mismatch";
                case 124: return "installation_timeout";
                default: return "installation_failed";
            }
        }

        private string PhaseExplanation()
        {
            switch (installPhase)
            {
                case "validate_configuration": return "설치 파일의 연결 설정을 확인하지 못했습니다. 관리자에게 새 설치 파일을 요청하세요.";
                case "validate_existing": return "기존 설치, 다른 설치 작업 또는 설치 경로를 확인하지 못했습니다. 다른 설치 창을 닫고 관리자에게 기존 등록 상태를 확인해 주세요.";
                case "protect_files": return "설치 경로의 소유자·접근 권한을 확인하지 못했습니다. 관리자에게 설치 폴더 권한을 확인해 달라고 요청하세요.";
                case "stop_previous": return "기존 Windows 서비스를 중지하지 못했습니다. 서비스와 파일 사용 상태를 확인한 뒤 다시 설치하세요.";
                case "preserve_configuration": return "기존 등록 정보를 안전하게 보존하지 못했습니다. 등록 정보를 지우지 말고 관리자에게 복구 설치 파일을 요청하세요.";
                case "write_files": return "설치 파일을 저장하지 못했습니다. 디스크 여유 공간, 파일 사용 상태와 폴더 권한을 확인하세요.";
                case "configure_service": return "Windows 서비스 또는 자동 복구 설정에 실패했습니다. 관리자 권한과 Windows 서비스 관리 상태를 확인하세요.";
                case "register_application": return "Windows 앱 등록에 실패했습니다. 관리자에게 레지스트리 접근 권한을 확인해 달라고 요청하세요.";
                case "create_status_shortcut": return "연결 상태 바로가기를 만들지 못했습니다. 공용 시작 메뉴 권한 또는 같은 이름의 다른 바로가기를 확인하세요.";
                case "start_service": return "설치한 서비스를 실행하지 못했습니다. Windows 서비스와 진단 로그를 확인한 뒤 복구 설치하세요.";
                case "rollback_failed": return "설치 실패 후 이전 상태를 완전히 복구하지 못했습니다. 자동으로 파일을 지우지 말고 관리자에게 복구 설치를 요청하세요.";
                default: return "설치 실행을 완료하지 못했습니다. 표시된 단계와 종료 코드를 관리자에게 전달하세요.";
            }
        }

        private void ShowInstallFailure(string code, int exitCode)
        {
            if (IsDisposed) return;
            busy = false;
            checking = false;
            complete = false;
            ResultExitCode = exitCode == 0 ? 20 : exitCode;
            connectionTimer.Stop();
            ControlBox = true;
            primary.Enabled = true;
            primary.Text = "설치 다시 시도";
            cancel.Enabled = true;
            cancel.Visible = true;
            cancel.Text = "닫기";
            diagnostics.Visible = Directory.Exists(Program.InstallRoot);
            progress.Style = ProgressBarStyle.Continuous;
            progress.Value = 0;
            title.Text = "설치를 완료하지 못했습니다";
            subtitle.Text = "연결 또는 설치 오류가 확인되어 성공으로 처리하지 않았습니다.";
            if (configuredEndpoint != "") subtitle.Text += "\r\n" + configuredEndpoint;
            status.ForeColor = Color.FromArgb(167, 36, 36);
            status.Text = "오류 코드: " + code + (exitCode == 0 ? "" : " / " + exitCode.ToString(CultureInfo.InvariantCulture));
            details.Text = code == "installation_failed" ? PhaseExplanation() :
                code == "installation_timeout" ? "설치 실행 시간이 초과됐습니다. 설치가 일부 진행됐을 수 있으므로 진단 로그와 Windows 서비스 상태를 확인한 뒤 복구 설치하세요."
                : ConnectionDiagnostics.Explain(code);
            details.Text += "\r\n\r\n확인 단계: " + installPhase;
            note.Text = "등록 정보를 임의로 삭제하지 마세요. 문제가 계속되면 운영 서버에서 복구 설치 파일을 발급받으세요.";
        }

        private async Task RunInstall()
        {
            DateTime verificationStart = DateTime.UtcNow;
            installPhase = "server_preflight";
            SetBusy("운영 서버 주소와 연결 준비 상태를 확인하는 중…");
            try
            {
                // Read and validate the package before creating a staging directory,
                // writing a payload, stopping a service or changing Windows settings.
                await Task.Run(delegate
                {
                    Dictionary<string, object> config;
                    try { config = Program.ReadEmbeddedConfiguration(); }
                    catch (SetupConnectionException) { throw; }
                    catch { throw new SetupConnectionException("configuration_invalid"); }
                    configuredEndpoint = ConnectionDiagnostics.ValidateEndpoint(config).GetLeftPart(UriPartial.Authority) + ConnectionDiagnostics.Text(config, "apiPrefix");
                    ConnectionDiagnostics.CheckServerReadiness(config);
                });
            }
            catch (SetupConnectionException error) { ShowInstallFailure(error.Code, 0); return; }
            catch { ShowInstallFailure("ready_network", 0); return; }
            if (IsDisposed) return;
            SetBusy("서버 확인 완료. 서비스와 연결 상태 도구를 설치하는 중…");
            int result = await Task.Run(delegate
            {
                string stage = null;
                try
                {
                    stage = SafeFiles.NewStagingDirectory("install");
                    string script = Path.Combine(stage, "Install.ps1");
                    SafeFiles.WriteNewPrivateFile(script, Program.ReadResource(Program.PayloadResource));
                    SafeFiles.AssertNoReparse(Program.ExecutablePath);
                    return Program.RunScript(script, " -SetupExecutablePath " + Program.QuoteArgument(Program.ExecutablePath),
                        null, delegate(string phase) { installPhase = phase; });
                }
                catch { return 1; }
                finally { if (stage != null) SafeFiles.DeleteOwnInstallStage(stage); }
            });
            if (result != 0 && result != 76) { ShowInstallFailure(ScriptFailureCode(result), result); return; }
            installationWarningCode = result == 76 ? 76 : 0;
            installed = true;
            busy = false;
            await VerifyConnection(true, verificationStart);
        }

        private ConnectionCheck ReadConnectionCheck(DateTime minimumSuccessUtc)
        {
            try
            {
                SafeFiles.ValidateInstalledAgent();
                SafeFiles.AssertPrivate(Path.Combine(Program.InstallRoot, "SecurityPresenceService.exe"), false);
                installed = true;
                string path = Path.Combine(Program.InstallRoot, "runtime-status.json");
                if (!File.Exists(path)) return new ConnectionCheck { Code = "status_missing" };
                SafeFiles.AssertPrivate(path, false);
                Dictionary<string, object> runtime;
                using (FileStream stream = new FileStream(path, FileMode.Open, FileAccess.Read, FileShare.ReadWrite | FileShare.Delete))
                {
                    if (stream.Length > 16384) return new ConnectionCheck { Code = "status_invalid" };
                    using (StreamReader reader = new StreamReader(stream, Encoding.UTF8))
                        runtime = new JavaScriptSerializer { MaxJsonLength = 16384, RecursionLimit = 8 }
                            .Deserialize<Dictionary<string, object>>(reader.ReadToEnd());
                }
                if (ConnectionDiagnostics.Text(runtime, "code") == "configuration_invalid")
                    return ConnectionDiagnostics.EvaluateStatus(runtime, null, DateTime.UtcNow, minimumSuccessUtc);
                Dictionary<string, object> config;
                try { config = ReadInstallationConfig(); }
                catch { return new ConnectionCheck { Code = "configuration_invalid", NeedsAdmin = true, UpdatedUtc = ConnectionDiagnostics.Timestamp(runtime, "updatedUtc") }; }
                try { configuredEndpoint = ConnectionDiagnostics.ValidateEndpoint(config).GetLeftPart(UriPartial.Authority) + ConnectionDiagnostics.Text(config, "apiPrefix"); }
                catch (SetupConnectionException) { /* The fixed status code below explains invalid configuration. */ }
                return ConnectionDiagnostics.EvaluateStatus(runtime, config, DateTime.UtcNow, minimumSuccessUtc);
            }
            catch (FileNotFoundException) { return new ConnectionCheck { Code = "status_missing" }; }
            catch (DirectoryNotFoundException) { installed = false; return new ConnectionCheck { Code = "installation_missing" }; }
            catch { return new ConnectionCheck { Code = "status_invalid" }; }
        }

        private static string LocalTime(DateTime? value)
        {
            return value.HasValue ? value.Value.ToLocalTime().ToString("yyyy-MM-dd HH:mm:ss", CultureInfo.InvariantCulture) : "확인된 기록 없음";
        }

        private void RenderConnection(ConnectionCheck result)
        {
            if (IsDisposed) return;
            busy = false;
            complete = false;
            ResultExitCode = result.Connected ? 0 : 80;
            ControlBox = true;
            primary.Enabled = true;
            primary.Text = "연결 다시 확인";
            cancel.Enabled = true;
            cancel.Visible = true;
            cancel.Text = "닫기";
            diagnostics.Visible = installed;
            progress.Style = ProgressBarStyle.Continuous;
            progress.Value = result.Connected ? 100 : 0;
            if (result.Connected)
            {
                installationWarningCode = 0;
                title.Text = "서버 연결 확인 완료";
                subtitle.Text = "에이전트의 최근 인증된 상태 전송이 확인되었습니다.";
                if (configuredEndpoint != "") subtitle.Text += "\r\n" + configuredEndpoint;
                status.ForeColor = Color.FromArgb(0, 113, 80);
                status.Text = "현재 연결 확인됨 · 5초마다 연결 기록을 다시 확인합니다.";
                details.Text = "마지막 인증된 상태 전송: " + LocalTime(result.LastSuccessUtc) +
                    "\r\n상태 기록 갱신: " + LocalTime(result.UpdatedUtc) +
                    "\r\n\r\n설치 위치: " + Program.InstallRoot;
                note.Text = "이 창을 닫은 후에도 시작 메뉴의 ‘App-IT-Manager 연결 상태’에서 다시 확인할 수 있습니다.";
            }
            else
            {
                title.Text = "서버 연결 확인 실패";
                subtitle.Text = installed ? "서비스 파일은 설치되어 있지만 현재 연결 성공은 확인하지 못했습니다."
                    : "이 PC의 설치 또는 연결 상태를 확인하지 못했습니다.";
                if (configuredEndpoint != "") subtitle.Text += "\r\n" + configuredEndpoint;
                status.ForeColor = Color.FromArgb(167, 36, 36);
                status.Text = "상태 코드: " + result.Code +
                    (result.HttpStatus.HasValue ? " · HTTP " + result.HttpStatus.Value.ToString(CultureInfo.InvariantCulture) : "");
                details.Text = result.Code == "installation_missing"
                    ? "설치 정보를 찾을 수 없습니다. 운영 서버에서 발급한 설치 파일로 설치하거나 복구하세요."
                    : ConnectionDiagnostics.Explain(result.Code);
                details.Text += "\r\n\r\n마지막 연결 성공: " + LocalTime(result.LastSuccessUtc) +
                    "\r\n상태 기록 갱신: " + LocalTime(result.UpdatedUtc);
                note.Text = result.NeedsAdmin
                    ? "관리자의 등록 확인 또는 복구 설치가 필요합니다. 다시 확인 버튼은 인증 정보를 초기화하지 않습니다."
                    : "네트워크·서비스를 확인한 뒤 다시 확인하세요. 등록 상태가 불확실하므로 설치 정보를 자동 삭제하지 않습니다.";
                if (installationWarningCode != 0) note.Text = "서비스 시작 확인 코드 76. " + note.Text;
            }
        }

        private async Task VerifyConnection(bool waitForSuccess, DateTime minimumSuccessUtc)
        {
            if (checking || IsDisposed) return;
            checking = true;
            connectionTimer.Stop();
            if (waitForSuccess)
            {
                busy = false;
                ControlBox = true;
                primary.Enabled = false;
                cancel.Enabled = true;
                cancel.Visible = true;
                cancel.Text = "닫기";
                diagnostics.Visible = installed;
                progress.Style = ProgressBarStyle.Marquee;
                progress.MarqueeAnimationSpeed = 24;
                title.Text = "실제 서버 연결을 확인하는 중입니다";
                subtitle.Text = "최대 45초 동안 새 인증된 상태 전송을 기다립니다.";
                status.ForeColor = Color.FromArgb(28, 45, 61);
                status.Text = "서비스 설치만으로 연결 성공을 표시하지 않습니다.";
                note.Text = "창을 닫아도 서비스의 연결 재시도는 계속됩니다.";
            }
            ConnectionCheck result = new ConnectionCheck { Code = "status_missing" };
            Stopwatch deadline = Stopwatch.StartNew();
            try
            {
                do
                {
                    result = await Task.Run(delegate { return ReadConnectionCheck(minimumSuccessUtc); });
                    if (IsDisposed) return;
                    if (result.Connected || result.NeedsAdmin || !waitForSuccess || deadline.Elapsed.TotalSeconds >= 45) break;
                    await Task.Delay(1000);
                } while (!IsDisposed);
                RenderConnection(result);
            }
            finally
            {
                checking = false;
                if (!IsDisposed) connectionTimer.Start();
            }
        }

        private void OpenDiagnosticLog()
        {
            try
            {
                SafeFiles.AssertPrivate(Program.InstallRoot, true);
                string path = Path.Combine(Program.InstallRoot, "agent.log");
                if (!File.Exists(path)) path = Path.Combine(Program.InstallRoot, "service.log");
                SafeFiles.AssertPrivate(path, false);
                Process.Start(new ProcessStartInfo(Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.System), "notepad.exe"),
                    Program.QuoteArgument(path)) { UseShellExecute = false, WindowStyle = ProcessWindowStyle.Normal }).Dispose();
            }
            catch
            {
                MessageBox.Show(this, "진단 로그를 열지 못했습니다. 설치 폴더와 Windows 서비스 상태를 관리자에게 확인해 달라고 요청하세요.",
                    "진단 로그", MessageBoxButtons.OK, MessageBoxIcon.Information);
            }
        }

        private static string ConfigText(Dictionary<string, object> config, string key)
        {
            object value;
            return config.TryGetValue(key, out value) && value != null ? Convert.ToString(value, CultureInfo.InvariantCulture) : "";
        }

        private static Dictionary<string, object> ReadInstallationConfig()
        {
            string path = Path.Combine(Program.InstallRoot, "config.json");
            SafeFiles.AssertPrivate(Program.InstallRoot, true);
            SafeFiles.AssertPrivate(path, false);
            if (new FileInfo(path).Length > 16384) throw new InvalidDataException();
            JavaScriptSerializer serializer = new JavaScriptSerializer { MaxJsonLength = 16384, RecursionLimit = 12 };
            Dictionary<string, object> config = serializer.Deserialize<Dictionary<string, object>>(File.ReadAllText(path, Encoding.UTF8));
            if (config == null) throw new InvalidDataException();
            return config;
        }

        private static bool NeverRegisteredAutomatic(Dictionary<string, object> config)
        {
            Guid ticket;
            if (ConfigText(config, "registrationMode") != "automatic" || ConfigText(config, "apiPrefix") != "/api/v1/agent" ||
                !Guid.TryParseExact(ConfigText(config, "ticketId"), "D", out ticket) || ticket == Guid.Empty ||
                !Regex.IsMatch(ConfigText(config, "registrationToken"), "^[A-Za-z0-9_-]{43}$")) return false;
            foreach (string name in new[] { "deviceId", "deviceToken", "inventoryDeviceId", "enrollmentToken" })
                if (!String.IsNullOrEmpty(ConfigText(config, name))) return false;
            object prior;
            if (config.TryGetValue("hadPriorIdentity", out prior) && (!(prior is bool) || (bool)prior)) return false;
            return true;
        }

        private void BeginUninstall()
        {
            SetBusy("제거 작업을 준비하는 중…");
            string stage = null;
            bool launched = false;
            try
            {
                SafeFiles.ValidateInstalledAgent();
                stage = SafeFiles.NewStagingDirectory("uninstall");
                string helperPath = Path.Combine(stage, "SecurityPresenceSetup.exe");
                SafeFiles.AssertNoReparse(Program.ExecutablePath);
                SafeFiles.WriteNewPrivateFile(helperPath, File.ReadAllBytes(Program.ExecutablePath));
                SafeFiles.ValidateHelperPath(helperPath);
                using (Process current = Process.GetCurrentProcess())
                {
                    string arguments = "--uninstall-helper " + current.Id.ToString(CultureInfo.InvariantCulture) + " "
                        + current.StartTime.ToUniversalTime().Ticks.ToString(CultureInfo.InvariantCulture);
                    // This process owns the visible removal progress window; only its
                    // PowerShell child is hidden.
                    Process.Start(new ProcessStartInfo(helperPath, arguments)
                    {
                        UseShellExecute = false,
                        WorkingDirectory = stage,
                        WindowStyle = ProcessWindowStyle.Normal
                    }).Dispose();
                }
                launched = true;
                ResultExitCode = 0;
                busy = false;
                Close();
            }
            catch { Finish(1); }
            finally
            {
                if (!launched && stage != null)
                {
                    try
                    {
                        string failedHelper = Path.Combine(stage, "SecurityPresenceSetup.exe");
                        SafeFiles.ValidateHelperPath(failedHelper);
                        File.Delete(failedHelper);
                        Directory.Delete(stage, false);
                    }
                    catch { }
                }
            }
        }

        private async Task RunUninstallHelper()
        {
            string approvalCode = "";
            try
            {
                SafeFiles.ValidateInstalledAgent();
                Dictionary<string, object> configuration = ReadInstallationConfig();
                if (ConfigText(configuration, "apiPrefix") == "/api/v1/agent" && !NeverRegisteredAutomatic(configuration))
                {
                    approvalCode = RequestUninstallApproval();
                    if (approvalCode == null) { Finish(1223); return; }
                }
                else if (NeverRegisteredAutomatic(configuration))
                {
                    note.Text = "발급된 기기 정보가 아직 저장되지 않은 설치입니다. Windows 관리자 권한으로 정리합니다.";
                }
            }
            catch { Finish(1); return; }
            SetBusy("자동 실행을 중지하고 설치 파일을 제거하는 중…");
            int result = await Task.Run(delegate
            {
                try
                {
                    try
                    {
                        using (Process parent = Process.GetProcessById(parentPid))
                        {
                            if (parent.StartTime.ToUniversalTime().Ticks == parentTicks && !parent.WaitForExit(30000))
                                return 125;
                        }
                    }
                    catch (ArgumentException) { /* Parent has already exited. */ }
                    SafeFiles.ValidateHelperPath(Program.ExecutablePath);
                    SafeFiles.ValidateInstalledAgent();
                    return Program.RunScript(Path.Combine(Program.InstallRoot, "uninstall.ps1"), "", approvalCode);
                }
                catch { return 1; }
            });
            approvalCode = null;
            Finish(result);
        }

        private string RequestUninstallApproval()
        {
            using (Form dialog = new Form())
            using (TextBox input = new TextBox())
            {
                dialog.Text = "관리자 제거 승인";
                dialog.ClientSize = new Size(480, 180);
                dialog.FormBorderStyle = FormBorderStyle.FixedDialog;
                dialog.StartPosition = FormStartPosition.CenterParent;
                dialog.MinimizeBox = false;
                dialog.MaximizeBox = false;
                Label explanation = new Label { Text = "App IT Manager 관리자가 발급한 일회용 제거 승인 코드를 입력하세요.", AutoSize = false };
                explanation.SetBounds(20, 20, 440, 45);
                input.SetBounds(20, 75, 440, 28);
                input.UseSystemPasswordChar = true;
                input.MaxLength = 128;
                Button confirm = new Button { Text = "승인 확인", DialogResult = DialogResult.OK };
                confirm.SetBounds(260, 125, 95, 32);
                Button cancelButton = new Button { Text = "취소", DialogResult = DialogResult.Cancel };
                cancelButton.SetBounds(365, 125, 95, 32);
                dialog.Controls.AddRange(new Control[] { explanation, input, confirm, cancelButton });
                dialog.AcceptButton = confirm;
                dialog.CancelButton = cancelButton;
                if (dialog.ShowDialog(this) != DialogResult.OK) return null;
                string code = input.Text.Trim();
                input.Clear();
                if (!System.Text.RegularExpressions.Regex.IsMatch(code, "^[A-Za-z0-9_-]{24,128}$"))
                {
                    MessageBox.Show(this, "유효한 관리자 승인 코드를 입력해 주세요.", "승인 코드 확인", MessageBoxButtons.OK, MessageBoxIcon.Information);
                    return null;
                }
                return code;
            }
        }
    }
}
