local aes = require "resty.aes"
local bit = require "bit"
local hmac_sha256 = require "utils.hmac_sha256"
local random = require "resty.random"
local str = require "resty.string"

local _M = { _VERSION = "0.1-openssl3" }
local mt = { __index = _M }

local SPEC_VERSION = 0x80

local function urlsafe_b64decode(value)
  value = value:gsub("-", "+")
  value = value:gsub("_", "/")
  return ngx.decode_base64(value)
end

local function urlsafe_b64encode(bytes)
  local value = ngx.encode_base64(bytes)
  value = value:gsub("+", "-")
  value = value:gsub("/", "_")
  return value
end

local function pack_int(int, n)
  if int == 0 then
    return string.char(0):rep(n)
  end

  local bytes = ""
  for i = n * 6, 0, -8 do
    bytes = bytes .. string.char(bit.rshift(int, i) % 256)
  end
  return bytes
end

local function unpack_int(bytes)
  return tonumber(str.to_hex(bytes), 16)
end

local function hmac(key, data)
  return hmac_sha256.raw(key, data)
end

function _M.generate_key()
  return urlsafe_b64encode(random.bytes(32))
end

function _M.new(self, key)
  local decoded = assert(urlsafe_b64decode(key))
  return setmetatable({
    signing_key = decoded:sub(1, 16),
    encryption_key = decoded:sub(17, 32)
  }, mt)
end

function _M._time()
  return os.time()
end

function _M._iv()
  return random.bytes(16)
end

function _M.encrypt(self, secret)
  if type(secret) ~= "string" then
    return nil, "secret must be a string"
  end

  local current_time = self:_time()
  local iv = self:_iv()
  local aes_128_cbc_with_iv = aes:new(self.encryption_key, nil, aes.cipher(128, "cbc"), { iv = iv })
  if aes_128_cbc_with_iv == nil then
    return nil, "invalid key or iv"
  end

  local ciphertext = aes_128_cbc_with_iv:encrypt(secret)
  local head = string.char(SPEC_VERSION) .. pack_int(0, 4) .. pack_int(current_time, 4) .. iv .. ciphertext

  local mac, err = hmac(self.signing_key, head)
  if err then
    return nil, err
  end

  return urlsafe_b64encode(head .. mac), nil
end

function _M.decrypt(self, token, ttl)
  if type(token) ~= "string" then
    return nil, "token must be a string"
  end

  local data = urlsafe_b64decode(token)
  if data == nil then
    return nil, "invalid base64"
  end

  if (#data - 57) % 16 ~= 0 then
    return nil, "invalid data size"
  end

  local version = data:byte(1)
  if version ~= SPEC_VERSION then
    return nil, "invalid version"
  end

  local issued_time = unpack_int(data:sub(2, 9))
  local current_time = self:_time()
  local time_diff = current_time - issued_time
  if time_diff < 0 then
    return nil, "unacceptable clock skew"
  end

  if ttl and time_diff > ttl then
    return nil, "token has expired"
  end

  local mac_a = data:sub(#data - 31)
  local mac_b, err = hmac(self.signing_key, data:sub(1, #data - 32))
  if err then
    return nil, err
  end

  if mac_a ~= mac_b then
    return nil, "hmac digests do not match"
  end

  local iv = data:sub(10, 25)
  local ciphertext = data:sub(26, #data - 32)
  local aes_128_cbc_with_iv = aes:new(self.encryption_key, nil, aes.cipher(128, "cbc"), { iv = iv })
  if aes_128_cbc_with_iv == nil then
    return nil, "invalid key or iv"
  end

  local secret = aes_128_cbc_with_iv:decrypt(ciphertext)
  if secret == nil then
    return nil, "could not decrypt ciphertext"
  end

  return secret, nil
end

return _M
