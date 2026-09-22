/**
 * Shared Core Configurator client for Mission Control panels.
 * Loaded via extra_module_url before feature panels.
 *
 * window.CoreConfigurator.getUrl(hass, key)          → Promise<string>
 * window.CoreConfigurator.getServices(hass)           → Promise<Service[]>
 * window.CoreConfigurator.setService(hass, key, opts) → Promise<void>
 * window.CoreConfigurator.subscribe(hass, callback)   → Promise<unsub>
 *
 * All calls are fail-safe: network errors return "" or []. No hardcoded IPs.
 */
(function attachCoreConfigurator(global) {
  const TYPE_GET = "core_configurator/get_url";
  const TYPE_LIST = "core_configurator/get_services";
  const TYPE_SET = "core_configurator/set_service";
  const EVENT = "core_configurator_updated";

  function strip(url) {
    return String(url || "").replace(/\/$/, "");
  }

  async function getUrl(hass, key) {
    if (!hass?.connection) return "";
    try {
      const res = await hass.connection.sendMessagePromise({ type: TYPE_GET, key });
      return strip(res.url || "");
    } catch (_) {
      return "";
    }
  }

  async function getServices(hass) {
    if (!hass?.connection) return [];
    try {
      const res = await hass.connection.sendMessagePromise({ type: TYPE_LIST });
      return res.services || [];
    } catch (_) {
      return [];
    }
  }

  async function setService(hass, key, { url, extra } = {}) {
    const msg = { type: TYPE_SET, key };
    if (url != null) msg.url = url;
    if (extra != null) msg.extra = extra;
    return hass.connection.sendMessagePromise(msg);
  }

  async function subscribe(hass, callback) {
    if (!hass?.connection) return () => {};
    return hass.connection.subscribeEvents((ev) => {
      callback(ev.data || {});
    }, EVENT);
  }

  global.CoreConfigurator = { getUrl, getServices, setService, subscribe };
})(typeof window !== "undefined" ? window : globalThis);
