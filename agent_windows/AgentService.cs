using System;
using System.Diagnostics;
using System.IO;
using System.Reflection;
using System.Runtime.InteropServices;
using System.Security.AccessControl;
using System.Security.Principal;
using System.ServiceProcess;
using System.Threading;
using System.Text;
using System.Net;
using System.Collections.Generic;
using System.Web.Script.Serialization;
using System.Globalization;
using System.Security.Cryptography;

[assembly: AssemblyTitle("Security Presence Service")]
[assembly: AssemblyCompany("Security Presence")]
[assembly: AssemblyProduct("Security Presence Agent")]
[assembly: AssemblyVersion("0.5.0.0")]
[assembly: AssemblyFileVersion("0.5.0.0")]

namespace SecurityPresence
{
    internal sealed class AgentService : ServiceBase
    {
        private readonly object gate = new object();
        private readonly ManualResetEvent stopping = new ManualResetEvent(false);
        private readonly AutoResetEvent healthChanged = new AutoResetEvent(false);
        private readonly string root = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.CommonApplicationData), "SecurityPresenceAgent");
        private Thread worker;
        private Thread reporter;
        private Process child;
        private IntPtr childJob = IntPtr.Zero;
        private HttpWebRequest healthRequest;
        private string readyFingerprint;
        private Stopwatch readyAge;
        private string lastRuntimeCode;
        private DateTimeOffset serviceStartedAt;
        private const string EventSource = "SecurityPresenceAgent";

        private AgentService()
        {
            ServiceName = "SecurityPresenceAgent";
            CanStop = true;
            CanShutdown = true;
            CanPauseAndContinue = false;
            AutoLog = false;
        }

        private static int Main(string[] args)
        {
            if (args.Length == 1 && (args[0] == "--configure-recovery" || args[0] == "--configure-diagnostics"))
            {
                try
                {
                    WindowsPrincipal principal = new WindowsPrincipal(WindowsIdentity.GetCurrent());
                    if (!principal.IsInRole(WindowsBuiltInRole.Administrator)) return 5;
                    AgentService service = new AgentService();
                    service.ValidateInstallation();
                    if (args[0] == "--configure-recovery") ConfigureRecovery();
                    EnsureEventSource();
                    return 0;
                }
                catch { return 1; }
            }
            if (args.Length != 0) return 2;
            ServiceBase.Run(new AgentService());
            return 0;
        }

        private static void EnsureEventSource()
        {
            // Optional diagnostics must never prevent an otherwise valid install.
            try
            {
                if (!EventLog.SourceExists(EventSource))
                    EventLog.CreateEventSource(new EventSourceCreationData(EventSource, "Application"));
            }
            catch { }
        }

        [StructLayout(LayoutKind.Sequential)]
        private struct FailureActions
        {
            public uint ResetPeriod;
            public IntPtr RebootMessage;
            public IntPtr Command;
            public uint Count;
            public IntPtr Actions;
        }
        [DllImport("advapi32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
        private static extern IntPtr OpenSCManager(string machine, string database, uint access);
        [DllImport("advapi32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
        private static extern IntPtr OpenService(IntPtr manager, string name, uint access);
        [DllImport("advapi32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
        private static extern bool ChangeServiceConfig2(IntPtr service, uint level, ref FailureActions actions);
        [DllImport("advapi32.dll")]
        private static extern bool CloseServiceHandle(IntPtr handle);

        private static void ConfigureRecovery()
        {
            IntPtr manager = OpenSCManager(null, null, 1);
            if (manager == IntPtr.Zero) throw new System.ComponentModel.Win32Exception(Marshal.GetLastWin32Error());
            IntPtr service = IntPtr.Zero;
            IntPtr actions = IntPtr.Zero;
            try
            {
                service = OpenService(manager, "SecurityPresenceAgent", 0x12); // CHANGE_CONFIG | START for restart recovery
                if (service == IntPtr.Zero) throw new System.ComponentModel.Win32Exception(Marshal.GetLastWin32Error());
                // Three ordinary SCM restarts, then SC_ACTION_NONE. No reboot,
                // shell command, or restart after an administrator's clean stop.
                int[] values = { 1, 60000, 1, 120000, 1, 300000, 0, 0 };
                actions = Marshal.AllocHGlobal(values.Length * 4);
                Marshal.Copy(values, 0, actions, values.Length);
                FailureActions settings = new FailureActions();
                settings.ResetPeriod = 86400;
                settings.Count = 4;
                settings.Actions = actions;
                if (!ChangeServiceConfig2(service, 2, ref settings))
                    throw new System.ComponentModel.Win32Exception(Marshal.GetLastWin32Error());
            }
            finally
            {
                if (actions != IntPtr.Zero) Marshal.FreeHGlobal(actions);
                if (service != IntPtr.Zero) CloseServiceHandle(service);
                CloseServiceHandle(manager);
            }
        }

        [StructLayout(LayoutKind.Sequential)]
        private struct JobBasicLimits
        {
            public long ProcessTime, JobTime;
            public uint Flags;
            public UIntPtr MinimumWorkingSet, MaximumWorkingSet;
            public uint ActiveProcesses;
            public UIntPtr Affinity;
            public uint PriorityClass, SchedulingClass;
        }
        [StructLayout(LayoutKind.Sequential)]
        private struct JobLimits
        {
            public JobBasicLimits Basic;
            public ulong ReadOperations, WriteOperations, OtherOperations, ReadBytes, WriteBytes, OtherBytes;
            public UIntPtr ProcessMemory, JobMemory, PeakProcessMemory, PeakJobMemory;
        }
        [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode)]
        private struct StartupInfo
        {
            public uint Size;
            public string Reserved, Desktop, Title;
            public uint X, Y, XSize, YSize, XChars, YChars, Fill, Flags;
            public ushort ShowWindow, ReservedSize;
            public IntPtr ReservedBytes, Input, Output, Error;
        }
        [StructLayout(LayoutKind.Sequential)]
        private struct ProcessInfo { public IntPtr Process, Thread; public uint ProcessId, ThreadId; }
        [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
        private static extern IntPtr CreateJobObject(IntPtr attributes, string name);
        [DllImport("kernel32.dll", SetLastError = true)]
        private static extern bool SetInformationJobObject(IntPtr job, int informationClass, ref JobLimits limits, uint size);
        [DllImport("kernel32.dll", SetLastError = true)]
        private static extern bool AssignProcessToJobObject(IntPtr job, IntPtr process);
        [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
        private static extern bool CreateProcess(string application, StringBuilder command, IntPtr processAttributes, IntPtr threadAttributes,
            bool inheritHandles, uint flags, IntPtr environment, string directory, ref StartupInfo startup, out ProcessInfo process);
        [DllImport("kernel32.dll", SetLastError = true)]
        private static extern uint ResumeThread(IntPtr thread);
        [DllImport("kernel32.dll", SetLastError = true)]
        private static extern bool TerminateProcess(IntPtr process, uint code);
        [DllImport("kernel32.dll")]
        private static extern bool CloseHandle(IntPtr handle);

        // Called under gate. No agent code runs until it is attached to this
        // private kill-on-close job; wrapper death also terminates its children.
        private Process StartAgentInJob(string powershell)
        {
            IntPtr job = CreateJobObject(IntPtr.Zero, null);
            if (job == IntPtr.Zero) throw new System.ComponentModel.Win32Exception(Marshal.GetLastWin32Error());
            ProcessInfo process = new ProcessInfo();
            IntPtr environment = IntPtr.Zero;
            Process managed = null;
            bool success = false;
            try
            {
                JobLimits limits = new JobLimits();
                limits.Basic.Flags = 0x2000; // JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
                if (!SetInformationJobObject(job, 9, ref limits, (uint)Marshal.SizeOf(typeof(JobLimits))))
                    throw new System.ComponentModel.Win32Exception(Marshal.GetLastWin32Error());
                System.Collections.Generic.SortedDictionary<string, string> values = new System.Collections.Generic.SortedDictionary<string, string>(StringComparer.OrdinalIgnoreCase);
                foreach (System.Collections.DictionaryEntry item in Environment.GetEnvironmentVariables())
                    values[(string)item.Key] = (string)item.Value;
                values["PSModulePath"] = Path.Combine(Path.GetDirectoryName(powershell), "Modules");
                StringBuilder block = new StringBuilder();
                foreach (System.Collections.Generic.KeyValuePair<string, string> item in values)
                    block.Append(item.Key).Append('=').Append(item.Value).Append('\0');
                block.Append('\0');
                environment = Marshal.StringToHGlobalUni(block.ToString());
                StartupInfo startup = new StartupInfo();
                startup.Size = (uint)Marshal.SizeOf(typeof(StartupInfo));
                startup.Flags = 1; // STARTF_USESHOWWINDOW, SW_HIDE=0
                string command = "\"" + powershell + "\" -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -File \"" + Path.Combine(root, "agent.ps1") + "\"";
                if (!CreateProcess(powershell, new StringBuilder(command), IntPtr.Zero, IntPtr.Zero, false,
                    0x08000000 | 0x00000400 | 0x00000004, environment, root, ref startup, out process))
                    throw new System.ComponentModel.Win32Exception(Marshal.GetLastWin32Error());
                if (!AssignProcessToJobObject(job, process.Process))
                    throw new System.ComponentModel.Win32Exception(Marshal.GetLastWin32Error());
                managed = Process.GetProcessById((int)process.ProcessId);
                if (ResumeThread(process.Thread) == UInt32.MaxValue)
                    throw new System.ComponentModel.Win32Exception(Marshal.GetLastWin32Error());
                childJob = job;
                success = true;
                return managed;
            }
            finally
            {
                if (!success)
                {
                    if (process.Process != IntPtr.Zero) TerminateProcess(process.Process, 1);
                    CloseHandle(job);
                    if (managed != null) managed.Dispose();
                }
                if (process.Thread != IntPtr.Zero) CloseHandle(process.Thread);
                if (process.Process != IntPtr.Zero) CloseHandle(process.Process);
                if (environment != IntPtr.Zero) Marshal.FreeHGlobal(environment);
            }
        }

        private void CloseChildJob()
        {
            if (childJob != IntPtr.Zero) { CloseHandle(childJob); childJob = IntPtr.Zero; }
        }

        private static bool Trusted(IdentityReference identity)
        {
            string sid = identity.Translate(typeof(SecurityIdentifier)).Value;
            return sid == "S-1-5-18" || sid == "S-1-5-32-544";
        }

        private static void AssertPrivate(string path, bool directory)
        {
            string current = Path.GetFullPath(path);
            while (!String.IsNullOrEmpty(current))
            {
                if ((File.GetAttributes(current) & FileAttributes.ReparsePoint) != 0)
                    throw new InvalidOperationException("Reparse path refused.");
                DirectoryInfo parent = Directory.GetParent(current);
                current = parent == null ? null : parent.FullName;
            }
            FileSystemSecurity acl = directory
                ? (FileSystemSecurity)Directory.GetAccessControl(path)
                : File.GetAccessControl(path);
            if (!Trusted(acl.GetOwner(typeof(SecurityIdentifier))))
                throw new InvalidOperationException("Unexpected owner.");
            foreach (FileSystemAccessRule rule in acl.GetAccessRules(true, true, typeof(SecurityIdentifier)))
                if (rule.AccessControlType == AccessControlType.Allow && !Trusted(rule.IdentityReference))
                    throw new InvalidOperationException("Unexpected file access.");
        }

        private void ValidateHostInstallation()
        {
            string expected = Path.Combine(root, "SecurityPresenceService.exe");
            if (!String.Equals(Path.GetFullPath(Assembly.GetExecutingAssembly().Location), expected, StringComparison.OrdinalIgnoreCase))
                throw new InvalidOperationException("Unexpected service executable path.");
            AssertPrivate(root, true);
            foreach (string name in new[] { "SecurityPresenceService.exe", ".security-presence-managed" })
                AssertPrivate(Path.Combine(root, name), false);
            if (File.ReadAllText(Path.Combine(root, ".security-presence-managed")).Trim() != "SecurityPresenceAgent/1")
                throw new InvalidOperationException("Unexpected installation marker.");
        }

        private void ValidateInstallation()
        {
            ValidateHostInstallation();
            AssertPrivate(Path.Combine(root, "agent.ps1"), false);
            AssertPrivate(Path.Combine(root, "config.json"), false);
        }

        private Dictionary<string, object> ReadPrivateJson(string name)
        {
            ValidateHostInstallation();
            if (name != "config.json" && name != "runtime-status.json") throw new InvalidDataException("Unexpected diagnostic file.");
            string path = Path.Combine(root, name);
            AssertPrivate(path, false);
            using (FileStream stream = new FileStream(path, FileMode.Open, FileAccess.Read, FileShare.ReadWrite | FileShare.Delete))
            {
                if (stream.Length > 16384) throw new InvalidDataException("Configuration size invalid.");
                using (StreamReader reader = new StreamReader(stream, Encoding.UTF8))
                {
                    JavaScriptSerializer serializer = new JavaScriptSerializer { MaxJsonLength = 16384, RecursionLimit = 12 };
                    Dictionary<string, object> config = serializer.Deserialize<Dictionary<string, object>>(reader.ReadToEnd());
                    if (config == null) throw new InvalidDataException("Configuration invalid.");
                    return config;
                }
            }
        }

        private Dictionary<string, object> ReadHealthConfiguration() { return ReadPrivateJson("config.json"); }

        private static string ConfigString(Dictionary<string, object> config, string key)
        {
            object value;
            return config.TryGetValue(key, out value) ? value as string : null;
        }

        private static Uri ValidateServerOrigin(Dictionary<string, object> config)
        {
            Uri server;
            if (!Uri.TryCreate(ConfigString(config, "serverUrl"), UriKind.Absolute, out server) ||
                server.AbsolutePath != "/" || !String.IsNullOrEmpty(server.UserInfo) || !String.IsNullOrEmpty(server.Query) || !String.IsNullOrEmpty(server.Fragment))
                throw new InvalidDataException("Health endpoint invalid.");
            string mode = ConfigString(config, "deploymentMode");
            if (config.ContainsKey("deploymentMode") && mode == null) throw new InvalidDataException("Deployment policy invalid.");
            if (mode != null && mode != "production" && mode != "development") throw new InvalidDataException("Deployment policy invalid.");
            string host = server.DnsSafeHost.Trim('[', ']').TrimEnd('.').ToLowerInvariant();
            bool local = server.IsLoopback || host == "localhost" || host.EndsWith(".localhost", StringComparison.Ordinal) || host == "localhost.localdomain";
            IPAddress address;
            if (IPAddress.TryParse(host, out address))
            {
                if (address.IsIPv4MappedToIPv6) address = address.MapToIPv4();
                local |= IPAddress.IsLoopback(address) || address.Equals(IPAddress.Any) || address.Equals(IPAddress.IPv6Any);
            }
            if (mode == "production")
            {
                if (server.Scheme != "https" || local) throw new InvalidDataException("Production origin invalid.");
            }
            else if (server.Scheme != "https" && !(server.Scheme == "http" && server.IsLoopback)) throw new InvalidDataException("Health endpoint invalid.");
            return server;
        }

        private static bool ValidReadiness(Dictionary<string, object> response, string expected)
        {
            object protocol, registrationReady;
            DateTimeOffset time;
            return response != null && ConfigString(response, "product") == "app-it-manager-agent" &&
                response.TryGetValue("protocol", out protocol) && (protocol is int || protocol is long) && Convert.ToInt64(protocol, CultureInfo.InvariantCulture) == 1 &&
                response.TryGetValue("registrationReady", out registrationReady) && registrationReady is bool && (bool)registrationReady &&
                String.Equals(ConfigString(response, "serverId"), expected, StringComparison.OrdinalIgnoreCase) &&
                System.Text.RegularExpressions.Regex.IsMatch(ConfigString(response, "latestAgentVersion") ?? "", "^\\d+\\.\\d+\\.\\d+$") &&
                DateTimeOffset.TryParse(ConfigString(response, "serverTime"), CultureInfo.InvariantCulture, DateTimeStyles.None, out time);
        }

        private void VerifyServerIdentity(Dictionary<string, object> config, Uri server, string prefix)
        {
            string expected = ConfigString(config, "expectedServerId");
            if (config.ContainsKey("expectedServerId") && expected == null) throw new InvalidDataException("Server identity invalid.");
            if (expected == null && ConfigString(config, "deploymentMode") != "production") return;
            if (expected == null || !System.Text.RegularExpressions.Regex.IsMatch(expected, "^[A-Fa-f0-9]{64}$"))
                throw new InvalidDataException("Server identity missing or invalid.");
            string fingerprint;
            using (SHA256 sha = SHA256.Create())
                fingerprint = Convert.ToBase64String(sha.ComputeHash(Encoding.UTF8.GetBytes(new JavaScriptSerializer().Serialize(config))));
            if (readyFingerprint == fingerprint && readyAge != null && readyAge.ElapsedMilliseconds < 60000) return;
            readyFingerprint = null;
            HttpWebRequest request = (HttpWebRequest)WebRequest.Create(server.AbsoluteUri.TrimEnd('/') + prefix + "/ready");
            request.Method = "GET";
            request.AllowAutoRedirect = false;
            request.Timeout = 5000;
            request.ReadWriteTimeout = 5000;
            lock (gate)
            {
                if (stopping.WaitOne(0)) { request.Abort(); throw new OperationCanceledException(); }
                healthRequest = request;
            }
            try
            {
                using (HttpWebResponse response = (HttpWebResponse)request.GetResponse())
                {
                    if ((int)response.StatusCode != 200 || response.ContentLength > 16384) throw new InvalidDataException("Readiness response invalid.");
                    using (StreamReader reader = new StreamReader(response.GetResponseStream(), Encoding.UTF8))
                    {
                        char[] buffer = new char[16385];
                        int count = reader.ReadBlock(buffer, 0, buffer.Length);
                        if (count >= buffer.Length) throw new InvalidDataException("Readiness response oversized.");
                        JavaScriptSerializer serializer = new JavaScriptSerializer { MaxJsonLength = 16384, RecursionLimit = 12 };
                        if (!ValidReadiness(serializer.Deserialize<Dictionary<string, object>>(new string(buffer, 0, count)), expected))
                            throw new InvalidDataException("Readiness identity or protocol mismatch.");
                    }
                }
                readyFingerprint = fingerprint;
                readyAge = Stopwatch.StartNew();
            }
            finally { lock (gate) { if (Object.ReferenceEquals(healthRequest, request)) healthRequest = null; } }
        }

        private void ReportRuntimeCodeChange()
        {
            try
            {
                Dictionary<string, object> status = ReadPrivateJson("runtime-status.json");
                object version;
                if (!status.TryGetValue("version", out version) || !(version is int) || (int)version != 1) return;
                string code = ConfigString(status, "code");
                string[] allowed = { "starting", "configuration_invalid", "registration_pending", "registration_network_error", "registration_blocked", "registration_save_failed", "heartbeat_network_error", "authentication_failed", "heartbeat_connected" };
                if (Array.IndexOf(allowed, code) < 0 || code == lastRuntimeCode) return;
                if (code == "heartbeat_connected")
                {
                    DateTimeOffset succeeded;
                    if (!DateTimeOffset.TryParse(ConfigString(status, "lastSuccessUtc"), CultureInfo.InvariantCulture, DateTimeStyles.None, out succeeded) || succeeded < serviceStartedAt) return;
                }
                lastRuntimeCode = code;
                if (!EventLog.SourceExists(EventSource) || EventLog.LogNameFromSourceName(EventSource, ".") != "Application") return;
                EventLogEntryType type = code == "heartbeat_connected" || code == "starting" || code == "registration_pending"
                    ? EventLogEntryType.Information : EventLogEntryType.Warning;
                EventLog.WriteEntry(EventSource, "Security Presence runtime status: " + code, type, 5000);
            }
            catch { /* Diagnostic reads and optional Event Log writes never stop the service. */ }
        }

        private void ReportServiceHealth()
        {
            Dictionary<string, object> config = ReadHealthConfiguration();
            // Old standalone servers have no independent service-health API.
            string prefix = ConfigString(config, "apiPrefix");
            if (prefix != "/api/v1/agent" && prefix != "/manage/it/api/v1/agent") return;
            string id = ConfigString(config, "deviceId");
            string token = ConfigString(config, "deviceToken");
            Guid parsedId;
            if (!Guid.TryParseExact(id, "D", out parsedId) || parsedId == Guid.Empty || token == null ||
                !System.Text.RegularExpressions.Regex.IsMatch(token, "^[A-Za-z0-9_-]{43}$")) return;
            Uri server = ValidateServerOrigin(config);
            VerifyServerIdentity(config, server, prefix);
            string state;
            lock (gate)
            {
                if (stopping.WaitOne(0)) return;
                if (!File.Exists(Path.Combine(root, "agent.ps1"))) state = "worker_missing";
                else state = child != null && !child.HasExited ? "running" : "worker_stopped";
            }
            byte[] body = Encoding.UTF8.GetBytes(new JavaScriptSerializer().Serialize(new { deviceId = id, state = state }));
            HttpWebRequest request = (HttpWebRequest)WebRequest.Create(server.AbsoluteUri.TrimEnd('/') + prefix + "/service-health");
            request.Method = "POST";
            request.ContentType = "application/json; charset=utf-8";
            request.ContentLength = body.Length;
            request.AllowAutoRedirect = false;
            request.Timeout = 5000;
            request.ReadWriteTimeout = 5000;
            request.Headers[HttpRequestHeader.Authorization] = "Bearer " + token;
            lock (gate)
            {
                if (stopping.WaitOne(0)) { request.Abort(); return; }
                healthRequest = request;
            }
            try
            {
                using (Stream output = request.GetRequestStream()) output.Write(body, 0, body.Length);
                using (HttpWebResponse response = (HttpWebResponse)request.GetResponse())
                    if ((int)response.StatusCode < 200 || (int)response.StatusCode >= 300)
                        throw new InvalidOperationException("Health response rejected.");
                // Never read commands or refresh the agent heartbeat here.
            }
            finally
            {
                lock (gate) { if (Object.ReferenceEquals(healthRequest, request)) healthRequest = null; }
            }
        }

        private void RunHealthReporter()
        {
            try { ServicePointManager.SecurityProtocol |= SecurityProtocolType.Tls12; }
            catch { Log("Service health TLS initialization unavailable."); }
            WaitHandle[] signals = { stopping, healthChanged };
            while (!stopping.WaitOne(0))
            {
                Stopwatch interval = Stopwatch.StartNew();
                ReportRuntimeCodeChange();
                try { ReportServiceHealth(); }
                catch { if (!stopping.WaitOne(0)) Log("Service health report unavailable. Retrying."); }
                if (WaitHandle.WaitAny(signals, Math.Max(1, 15000 - (int)Math.Min(interval.ElapsedMilliseconds, 15000))) == 0) return;
            }
        }

        protected override void OnStart(string[] args)
        {
            // Keep the reporter alive when the worker script is missing; the
            // independent status must not be mistaken for a worker heartbeat.
            ValidateHostInstallation();
            lock (gate)
            {
                stopping.Reset();
                serviceStartedAt = DateTimeOffset.UtcNow;
                worker = new Thread(RunAgent);
                worker.IsBackground = true;
                worker.Name = "Security Presence agent supervisor";
                worker.Start();
                reporter = new Thread(RunHealthReporter);
                reporter.IsBackground = true;
                reporter.Name = "Security Presence service status";
                reporter.Start();
            }
            Log("Service started.");
        }

        private void RunAgent()
        {
            int failures = 0;
            while (!stopping.WaitOne(0))
            {
                Process current = null;
                try
                {
                    ValidateInstallation();
                    string powershell = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.Windows), "System32", "WindowsPowerShell", "v1.0", "powershell.exe");
                    lock (gate)
                    {
                        if (stopping.WaitOne(0)) return;
                        current = StartAgentInJob(powershell);
                        child = current;
                        healthChanged.Set();
                    }
                    DateTime started = DateTime.UtcNow;
                    current.WaitForExit();
                    if ((DateTime.UtcNow - started).TotalMinutes >= 5) failures = 0;
                    if (!stopping.WaitOne(0)) Log("Agent exited. Restart scheduled.");
                }
                catch (Exception error)
                {
                    if (!stopping.WaitOne(0)) Log("Agent launch failed. Type " + error.GetType().Name + ".");
                }
                finally
                {
                    lock (gate)
                    {
                        if (Object.ReferenceEquals(child, current)) child = null;
                        CloseChildJob();
                        healthChanged.Set();
                        if (current != null) current.Dispose();
                    }
                }
                failures = Math.Min(failures + 1, 6);
                if (stopping.WaitOne(Math.Min(60000, failures * 10000))) return;
            }
        }

        protected override void OnStop()
        {
            // Signal first, then serialize with process creation. Once set, no
            // launch can occur after the administrator's stop request.
            stopping.Set();
            Thread join;
            Thread reportJoin;
            Stopwatch stopDeadline = Stopwatch.StartNew();
            lock (gate)
            {
                if (healthRequest != null) { try { healthRequest.Abort(); } catch { } }
                CloseChildJob();
                join = worker;
                reportJoin = reporter;
            }
            if (join != null && !join.Join(10000))
                throw new InvalidOperationException("Agent process did not stop within the service timeout.");
            if (reportJoin != null && !reportJoin.Join((int)Math.Max(1, 15000 - stopDeadline.ElapsedMilliseconds)))
                throw new InvalidOperationException("Service reporter did not stop within the service timeout.");
            Log("Service stopped by Windows or an administrator.");
        }

        protected override void OnShutdown() { OnStop(); }

        private void Log(string message)
        {
            try
            {
                string log = Path.Combine(root, "service.log");
                string old = log + ".1";
                foreach (string path in new[] { log, old })
                    if (File.Exists(path)) AssertPrivate(path, false);
                if (File.Exists(log) && new FileInfo(log).Length >= 262144)
                {
                    if (File.Exists(old)) File.Delete(old);
                    File.Move(log, old);
                }
                File.AppendAllText(log, DateTime.UtcNow.ToString("o") + " " + message + Environment.NewLine);
            }
            catch { /* Never print configuration, credentials or process output. */ }
        }
    }
}
