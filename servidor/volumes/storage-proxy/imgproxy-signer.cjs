"use strict";

const crypto = require("node:crypto");

const SIGNER_INSTALLED_SYMBOL = Symbol.for("supabase.imgproxySignerInstalled");

function parseHexSecret(name, value) {
  const trimmed = typeof value === "string" ? value.trim() : "";
  if (
    trimmed.length < 2 ||
    trimmed.length % 2 !== 0 ||
    !/^[0-9a-fA-F]+$/.test(trimmed)
  ) {
    throw new Error(`${name} must be a valid non-empty even-length hex string`);
  }
  const buf = Buffer.from(trimmed, "hex");
  if (buf.length === 0) {
    throw new Error(`${name} decoded to an empty key buffer`);
  }
  return buf;
}

function assertNoPathTraversal(rawTail) {
  if (rawTail.includes("\0") || rawTail.includes("\\")) {
    throw new Error("Rejected unsafe characters in imgproxy local URL");
  }
  const normalizedRaw = rawTail.toLowerCase();
  if (
    normalizedRaw.includes("%2e") ||
    normalizedRaw.includes("%2f") ||
    normalizedRaw.includes("%5c") ||
    normalizedRaw.includes("%00") ||
    normalizedRaw.includes("%25")
  ) {
    throw new Error("Rejected encoded path traversal in imgproxy local URL");
  }
  const segments = rawTail.split("/");
  for (const segment of segments) {
    if (segment === "." || segment === "..") {
      throw new Error("Rejected path traversal segment in imgproxy local URL");
    }
    let decoded = segment;
    try {
      decoded = decodeURIComponent(segment);
    } catch {
      decoded = segment;
    }
    if (
      decoded === "." ||
      decoded === ".." ||
      decoded.includes("/") ||
      decoded.includes("\\") ||
      decoded.includes("\0")
    ) {
      throw new Error("Rejected encoded path traversal in imgproxy local URL");
    }
  }
}

function rebaseLocalPath(pathToSign, localRoot = "/var/lib/storage") {
  if (typeof pathToSign !== "string" || !pathToSign.startsWith("/")) {
    throw new Error("imgproxy path to sign must start with '/'");
  }
  const marker = "/plain/local://";
  const markerIdx = pathToSign.indexOf(marker);
  if (markerIdx === -1) {
    return pathToSign;
  }

  const head = pathToSign.slice(0, markerIdx + marker.length);
  const rawTail = pathToSign.slice(markerIdx + marker.length);
  assertNoPathTraversal(rawTail);

  const normalizedRoot = String(
    localRoot === undefined || localRoot === null ? "/var/lib/storage" : localRoot
  ).trim();
  const cleanRoot = normalizedRoot.replace(/^\/+/, "").replace(/\/+$/, "");
  if (cleanRoot.length === 0) {
    return pathToSign;
  }

  const strippedTail = rawTail.replace(/^\/+/, "");
  if (strippedTail === cleanRoot) {
    return `${head}/`;
  }
  if (strippedTail.startsWith(`${cleanRoot}/`)) {
    const relPath = strippedTail.slice(cleanRoot.length + 1);
    return `${head}/${relPath}`;
  }
  if (rawTail.startsWith("//")) {
    throw new Error(
      "Rejected imgproxy local path outside IMGPROXY_LOCAL_FILESYSTEM_ROOT"
    );
  }
  return `${head}/${strippedTail}`;
}

function signImgproxyUrl(urlInput, env = process.env) {
  const rawStr = urlInput instanceof URL ? urlInput.toString() : String(urlInput);
  const imgProxyBase = String((env && env.IMGPROXY_URL) || "")
    .trim()
    .replace(/\/+$/, "");
  if (!imgProxyBase) {
    return rawStr;
  }

  const publicPrefix = `${imgProxyBase}/public/`;
  if (!rawStr.startsWith(publicPrefix)) {
    return rawStr;
  }

  const keyBuf =
    env && Buffer.isBuffer(env._keyBuf)
      ? env._keyBuf
      : parseHexSecret("IMGPROXY_KEY", env && env.IMGPROXY_KEY);
  const saltBuf =
    env && Buffer.isBuffer(env._saltBuf)
      ? env._saltBuf
      : parseHexSecret("IMGPROXY_SALT", env && env.IMGPROXY_SALT);

  const rawPath = rawStr.slice((imgProxyBase + "/public").length);
  const localRoot =
    env && env.IMGPROXY_LOCAL_FILESYSTEM_ROOT !== undefined
      ? env.IMGPROXY_LOCAL_FILESYSTEM_ROOT
      : "/var/lib/storage";
  const pathToSign = rebaseLocalPath(rawPath, localRoot);

  const signature = crypto
    .createHmac("sha256", keyBuf)
    .update(saltBuf)
    .update(pathToSign)
    .digest("base64url");

  return `${imgProxyBase}/${signature}${pathToSign}`;
}

function installFetchSigner(env = process.env) {
  const imageTransformEnabled =
    String((env && env.IMAGE_TRANSFORMATION_ENABLED) || "").toLowerCase() ===
    "true";
  const rawUrl = String((env && env.IMGPROXY_URL) || "").trim();
  const rawKey = String((env && env.IMGPROXY_KEY) || "").trim();
  const rawSalt = String((env && env.IMGPROXY_SALT) || "").trim();

  if (imageTransformEnabled && (rawKey || rawSalt)) {
    parseHexSecret("IMGPROXY_KEY", rawKey);
    parseHexSecret("IMGPROXY_SALT", rawSalt);
  }

  if (!rawUrl || !rawKey || !rawSalt) {
    return false;
  }

  const keyBuf = parseHexSecret("IMGPROXY_KEY", rawKey);
  const saltBuf = parseHexSecret("IMGPROXY_SALT", rawSalt);
  const imgProxyBase = rawUrl.replace(/\/+$/, "");
  const publicPrefix = `${imgProxyBase}/public/`;
  const compiledEnv = {
    IMGPROXY_URL: imgProxyBase,
    IMGPROXY_LOCAL_FILESYSTEM_ROOT:
      env.IMGPROXY_LOCAL_FILESYSTEM_ROOT !== undefined
        ? env.IMGPROXY_LOCAL_FILESYSTEM_ROOT
        : "/var/lib/storage",
    _keyBuf: keyBuf,
    _saltBuf: saltBuf,
  };

  if (
    typeof globalThis.fetch === "function" &&
    !globalThis.fetch[SIGNER_INSTALLED_SYMBOL]
  ) {
    const originalFetch = globalThis.fetch;
    const wrappedFetch = function imgproxySignedFetch(input, init) {
      if (typeof input === "string" || input instanceof URL) {
        const candidate = input instanceof URL ? input.toString() : input;
        if (candidate.startsWith(publicPrefix)) {
          const signed = signImgproxyUrl(candidate, compiledEnv);
          const nextInput = input instanceof URL ? new URL(signed) : signed;
          return Reflect.apply(originalFetch, this, [nextInput, init]);
        }
      }
      return Reflect.apply(originalFetch, this, [input, init]);
    };
    Object.defineProperty(wrappedFetch, SIGNER_INSTALLED_SYMBOL, {
      value: true,
      enumerable: false,
      configurable: false,
      writable: false,
    });
    globalThis.fetch = wrappedFetch;
  }
  return true;
}

installFetchSigner(process.env);

module.exports = {
  parseHexSecret,
  rebaseLocalPath,
  signImgproxyUrl,
  installFetchSigner,
};
