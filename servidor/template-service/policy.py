"""Fail-closed policy for author-supplied mail HTML and GoTrue placeholders."""

from __future__ import annotations

import re
from urllib.parse import urlsplit
import html5lib
import tinycss2

POLICY_VERSION = 1
FIELDS = {
    "Token",
    "TokenHash",
    "ConfirmationURL",
    "Email",
    "NewEmail",
    "SendingTo",
    "SiteURL",
    "RedirectTo",
    "Data",
}
ACTION = re.compile(r"{{(.*?)}}", re.S)
FIELD = re.compile(
    r"\.(?:Token|TokenHash|ConfirmationURL|Email|NewEmail|SendingTo|SiteURL|RedirectTo|Data(?:\.[A-Za-z_][A-Za-z0-9_]*)*)\Z"
)
MARKER = re.compile(r"zmailerplaceholder([0-9]+)z")
TAGS = set(
    "html head body title meta style div span p h1 h2 h3 h4 h5 h6 a img br hr table tr td th tbody thead tfoot caption colgroup col ul ol li pre code blockquote b strong em i u s small sub sup center font".split()
)
GLOBAL_ATTRS = set(
    "style class id align dir lang role aria-label aria-hidden title".split()
)
TAG_ATTRS = {
    "a": {"href", "target", "rel"},
    "img": {"src", "alt", "width", "height", "border"},
    "table": {"width", "height", "border", "cellpadding", "cellspacing", "bgcolor"},
    "td": {"width", "height", "colspan", "rowspan", "valign", "bgcolor"},
    "th": {"width", "height", "colspan", "rowspan", "valign", "bgcolor"},
    "tr": {"valign", "bgcolor"},
    "col": {"span", "width"},
    "font": {"color", "size", "face"},
    "meta": {"charset", "name", "content"},
}
CSS_FUNCTIONS = {
    "rgb",
    "rgba",
    "hsl",
    "hsla",
    "calc",
    "min",
    "max",
    "clamp",
    "linear-gradient",
    "radial-gradient",
}
CSS_PROPERTIES = set(
    """color background background-color margin margin-top margin-right margin-bottom margin-left
padding padding-top padding-right padding-bottom padding-left font font-family font-size font-weight font-style
font-variant line-height letter-spacing word-spacing text-align text-decoration text-transform text-indent
text-overflow white-space word-break overflow-wrap vertical-align border border-top border-right border-bottom
border-left border-width border-style border-color border-radius border-collapse border-spacing outline
outline-color outline-width outline-style width min-width max-width height min-height max-height display
box-sizing box-shadow opacity overflow overflow-x overflow-y list-style list-style-type table-layout float clear
position top right bottom left z-index flex flex-direction flex-wrap justify-content align-items gap row-gap
column-gap grid-template-columns grid-template-rows""".split()
)


class PolicyError(ValueError):
    pass


def origins(values):
    if not isinstance(values, list) or len(values) > 16:
        raise PolicyError("A política de destinos do projeto é inválida")
    result = set()
    for value in values:
        if not isinstance(value, str) or len(value) > 256:
            raise PolicyError("Origem inválida")
        parsed = urlsplit(value)
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.path not in ("", "/")
            or parsed.query
            or parsed.fragment
            or any(c in value for c in "\\%*\r\n\t ")
        ):
            raise PolicyError("Destinos devem ser origens HTTPS explícitas")
        try:
            port = parsed.port
        except ValueError:
            raise PolicyError("Porta inválida") from None
        host = parsed.hostname.encode("idna").decode().lower()
        if ":" in host:
            host = "[" + host + "]"
        result.add(
            "https://" + host + (":" + str(port) if port and port != 443 else "")
        )
    return sorted(result)


def symbolic(body):
    if "zmailerplaceholder" in body.lower():
        raise PolicyError("Marcador reservado no HTML")
    values = []
    depth = 0

    def replace(match):
        nonlocal depth
        action = match[1].strip()
        if action.startswith("-"):
            action = action[1:].lstrip()
        if action.endswith("-"):
            action = action[:-1].rstrip()
        if action.startswith("if "):
            if not FIELD.fullmatch(action[3:].strip()):
                raise PolicyError("Condição Go não permitida")
            depth += 1
            if depth > 16:
                raise PolicyError("Muitas condições aninhadas")
            return "<!-- mailer condition -->"
        if action == "else":
            return "<!-- mailer else -->"
        if action == "end":
            depth -= 1
            return "<!-- mailer end -->"
        if not FIELD.fullmatch(action):
            raise PolicyError(
                "Use variáveis diretas e if/else; funções, loops e definições não são permitidos"
            )
        values.append(action)
        return "zmailerplaceholder" + str(len(values) - 1) + "z"

    result = ACTION.sub(replace, body)
    if "{{" in result or depth != 0:
        raise PolicyError("Go template inválido")
    return result, values


def css_tokens(tokens):
    for token in tokens:
        if token.type in {"error", "url", "at-keyword"}:
            raise PolicyError("CSS com referências externas ou sintaxe inválida")
        if token.type == "function":
            if token.lower_name not in CSS_FUNCTIONS:
                raise PolicyError("Função CSS não permitida: " + token.lower_name)
            css_tokens(token.arguments)
        if hasattr(token, "content") and token.content is not None:
            css_tokens(token.content)


def css_declarations(tokens):
    for item in tinycss2.parse_declaration_list(
        tokens, skip_comments=True, skip_whitespace=True
    ):
        if item.type != "declaration" or item.lower_name not in CSS_PROPERTIES:
            raise PolicyError("Propriedade CSS não permitida")
        css_tokens(item.value)


def css(text, *, sheet=False):
    if MARKER.search(text):
        raise PolicyError("Variáveis não são permitidas em CSS")
    if len(text) > 131072:
        raise PolicyError("CSS excede 128 KB")
    if not sheet:
        css_declarations(text)
        return

    def rules(items, depth=0):
        if depth > 4:
            raise PolicyError("CSS muito aninhado")
        for rule in items:
            if rule.type == "qualified-rule":
                css_tokens(rule.prelude)
                css_declarations(rule.content)
            elif (
                rule.type == "at-rule"
                and rule.lower_at_keyword == "media"
                and rule.content is not None
            ):
                css_tokens(rule.prelude)
                rules(
                    tinycss2.parse_rule_list(
                        rule.content, skip_comments=True, skip_whitespace=True
                    ),
                    depth + 1,
                )
            else:
                raise PolicyError("Regra CSS não permitida")

    rules(tinycss2.parse_stylesheet(text, skip_comments=True, skip_whitespace=True))


def url(value, fields, approved, *, href, kind):
    if any(ord(c) <= 32 or ord(c) == 127 for c in value) or "\\" in value:
        raise PolicyError("URL inválida")
    matches = list(MARKER.finditer(value))
    if matches:
        names = [fields[int(m[1])] for m in matches]
        if (
            href
            and len(matches) == 1
            and value == matches[0][0]
            and names == [".ConfirmationURL"]
        ):
            return
        if (
            href
            and names
            and names[0] == ".SiteURL"
            and value.startswith(matches[0][0])
        ):
            suffix = value[len(matches[0][0]) :]
            # Keep the existing project verification flow, on the configured SiteURL.
            expected_type = {"magic_link": "magiclink", "confirmation": "signup"}.get(
                kind, kind
            )
            for m, name in zip(matches[1:], names[1:]):
                suffix = suffix.replace(m[0], "{{" + name + "}}")
            if not matches[1:] and (
                not suffix or re.fullmatch(r"/[A-Za-z0-9/_\-.]*", suffix)
            ):
                return
            if names == [".SiteURL", ".TokenHash"] and suffix in {
                "?token={{.TokenHash}}&type=" + expected_type,
                "?token_hash={{.TokenHash}}&type=" + expected_type,
            }:
                return
        raise PolicyError(
            "Variáveis em URLs: use .ConfirmationURL ou .SiteURL com o formato de verificação permitido. Imagens exigem URLs estáticas"
        )
    parsed = urlsplit(value)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
    ):
        raise PolicyError("Links e imagens devem usar HTTPS e um domínio aprovado")
    # Encoded authority, protocol-relative URLs and control characters are denied.
    origin = origins(["https://" + parsed.netloc])[0]
    if origin not in approved:
        raise PolicyError("Domínio não aprovado para este projeto: " + origin)


def validate(body, allowed_origins, kind):
    approved = origins(allowed_origins)
    if len(body.encode("utf-8")) > 1048576:
        raise PolicyError("HTML excede 1 MB")
    if body.count("<") > 5000:
        raise PolicyError("Muitos elementos HTML")
    source, fields = symbolic(body)
    required = (
        {".Token"}
        if kind == "reauthentication"
        else {".Token", ".TokenHash", ".ConfirmationURL"}
    )
    if not required.intersection(fields):
        raise PolicyError(
            "Inclua o código ou link de autenticação no conteúdo do e-mail"
        )
    parser = html5lib.HTMLParser(namespaceHTMLElements=False)
    document = parser.parse(source)
    # Reject duplicate attributes and malformed token boundaries rather than
    # trusting that every email client repairs broken HTML identically.
    fatal = {
        "duplicate-attribute",
        "unexpected-character-in-attribute-name",
        "invalid-character-in-attribute-name",
        "unexpected-character-after-attribute-value",
        "unexpected-EOF-after-attribute-value",
        "eof-in-attribute-value-double-quote",
        "eof-in-attribute-value-single-quote",
    }
    if any(error[1] in fatal for error in parser.errors):
        raise PolicyError("Atributos HTML inválidos ou duplicados")

    def visit(node, depth=0):
        if depth > 64:
            raise PolicyError("HTML muito aninhado")
        if not isinstance(node.tag, str):
            if (
                node.text
                and node.text.strip()
                and not node.text.strip().startswith(
                    ("mailer condition", "mailer else", "mailer end")
                )
            ):
                raise PolicyError("Comentários HTML não são permitidos")
            return
        if node.tag not in TAGS:
            raise PolicyError("Elemento HTML não permitido: " + node.tag)
        for name, value in node.attrib.items():
            if name not in GLOBAL_ATTRS | TAG_ATTRS.get(node.tag, set()):
                raise PolicyError("Atributo HTML não permitido: " + name)
            if name in {"href", "src"}:
                url(value, fields, approved, href=name == "href", kind=kind)
            elif name == "style":
                css(value)
            elif MARKER.search(value):
                raise PolicyError(
                    "Variáveis são permitidas no texto e nos links de autenticação"
                )
        if node.tag == "meta":
            if not (
                set(node.attrib) == {"charset"}
                and node.attrib["charset"].lower() == "utf-8"
            ):
                if not (
                    set(node.attrib) == {"name", "content"}
                    and node.attrib["name"].lower() == "viewport"
                ):
                    raise PolicyError("Meta HTML não permitida")
        if node.tag == "style":
            css("".join(node.itertext()), sheet=True)
        for child in node:
            visit(child, depth + 1)

    visit(document)
    return approved
