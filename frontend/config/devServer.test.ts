import { describe, expect, it } from "vitest";
import { allowedHosts, hmrClientPort } from "./devServer";

describe("allowedHosts", () => {
  it("takes the host names of the CORS origins (JSON list) so one setting covers the API and the dev server", () => {
    expect(
      allowedHosts({ AEROTWIN_CORS_ORIGINS: '["http://localhost:3005","https://aerotwin.wlan0.in","http://aerotwin.wlan0.in"]' }),
    ).toEqual(["localhost", "aerotwin.wlan0.in"]);
  });

  it("accepts a comma-separated list and bare host names", () => {
    expect(allowedHosts({ AEROTWIN_CORS_ORIGINS: "https://a.example.com, b.example.com:8443 ,c.example.com" })).toEqual([
      "a.example.com",
      "b.example.com",
      "c.example.com",
    ]);
  });

  it("adds VITE_ALLOWED_HOSTS, including Vite's leading-dot wildcard, without duplicates", () => {
    expect(
      allowedHosts({ AEROTWIN_CORS_ORIGINS: '["https://aerotwin.wlan0.in"]', VITE_ALLOWED_HOSTS: ".wlan0.in, aerotwin.wlan0.in" }),
    ).toEqual(["aerotwin.wlan0.in", ".wlan0.in"]);
  });

  it("allows every host when VITE_ALLOWED_HOSTS is all or true", () => {
    expect(allowedHosts({ VITE_ALLOWED_HOSTS: "all" })).toBe(true);
    expect(allowedHosts({ VITE_ALLOWED_HOSTS: "TRUE" })).toBe(true);
  });

  it("ignores blank, malformed and wildcard-origin entries instead of failing to start", () => {
    expect(allowedHosts({ AEROTWIN_CORS_ORIGINS: '["*", "", "not a url at all", "https://ok.example"]' })).toEqual(["ok.example"]);
    expect(allowedHosts({ AEROTWIN_CORS_ORIGINS: "[https://broken.example.com" })).toEqual(["broken.example.com"]);
    expect(allowedHosts({})).toEqual([]);
  });
});

describe("hmrClientPort", () => {
  it("is unset by default and parses a valid port", () => {
    expect(hmrClientPort({})).toBeUndefined();
    expect(hmrClientPort({ VITE_HMR_CLIENT_PORT: "443" })).toBe(443);
  });

  it("ignores an invalid port", () => {
    expect(hmrClientPort({ VITE_HMR_CLIENT_PORT: "abc" })).toBeUndefined();
    expect(hmrClientPort({ VITE_HMR_CLIENT_PORT: "70000" })).toBeUndefined();
  });
});
