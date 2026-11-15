# Authenticated desktop transport

GTK and `HttpService` accept HTTPS, or HTTP for actual loopback (`localhost`,
`127.0.0.1`, `[::1]`). They reject all other HTTP destinations except the
Tailscale CGNAT range `100.64.0.0/10` *after explicit per-host:port consent*.
The 100.64/10 address is **not proof** of an active WireGuard/Tailscale tunnel.
A user must check the VPN on their device, enable the GTK confirmation control
once per host, and monitor the persistent warning on the GTK main screen.
Stored consent survives restart under the local AUTOSEG connection settings;
it does not verify the tunnel. HTTP without VPN still risks credential exposure.

Preferred deployments:

- **Tailscale Serve HTTPS:** enable `tailscale serve` for the local AUTOSEG
  service, use its authenticated HTTPS URL in GTK and do not need HTTP consent.
- **SSH forwarding:** forward the server port to your laptop's `127.0.0.1`
  through an authenticated SSH connection; use `http://127.0.0.1:<port>`.

Auth requests never follow redirects to a new host or downgrade from TLS.
Do not use plain HTTP on LAN, the public internet or untrusted CGNAT networks.
