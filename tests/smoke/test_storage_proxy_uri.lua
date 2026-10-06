local proxy_uri = require("utils.proxy_uri")

local cases = {
    {"/storage/v1/object/sign/bucket/Captura de tela.png",
     "/storage/v1/object/sign/bucket/Captura%20de%20tela.png"},
    {"/storage/v1/object/public/bucket/pasta/ação.png",
     "/storage/v1/object/public/bucket/pasta/a%C3%A7%C3%A3o.png"},
    {"/storage/v1/object/bucket/100% + #?.png",
     "/storage/v1/object/bucket/100%25%20%2B%20%23%3F.png"},
    {"/storage/v1/object/bucket/literal%20.png",
     "/storage/v1/object/bucket/literal%2520.png"},
    {"/storage/v1/upload/resumable/YWJj", "/storage/v1/upload/resumable/YWJj"},
    {"/storage/v1/object/bucket/line\nfeed.png",
     "/storage/v1/object/bucket/line%0Afeed.png"},
}

for _, case in ipairs(cases) do
    assert(proxy_uri.escape_path(case[1]) == case[2], case[1])
end

ngx.say("Storage proxy URI encoding passed")
