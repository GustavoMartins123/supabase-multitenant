# Erro ao Executar Scripts (.sh) - CRLF / $'\r': command not found

## Descrição

Este erro ocorre ao executar scripts `.sh` em ambientes Linux quando os arquivos foram criados ou editados no Windows.

---

## Sintoma

Ao rodar o script:

```bash
sudo bash setup.sh
```

Erros como:

```bash
$'\r': command not found
: invalid option: set: -
syntax error near unexpected token `$'{\r''
```

---

## Causa

O arquivo `.sh` está com quebra de linha no formato **CRLF (Windows)**, enquanto o Linux utiliza **LF (Unix)**.

O caractere `\r` (carriage return) é interpretado como inválido pelo shell, causando erros de execução.

---

## Como Diagnosticar

Verifique o formato do arquivo:

```bash
file setup.sh
```

Se aparecer:

```
with CRLF line terminators
```

---

### Converter todos os scripts do projeto

```bash
find . -type f -name "*.sh" -exec sed -i 's/\r$//' {} +
```

---

### Converter apenas um arquivo

```bash
sed -i 's/\r$//' setup.sh
```

---

## Testar novamente

```bash
sudo bash setup.sh
```

---

## 💡 Observações

- Esse erro é muito comum em ambientes híbridos (Windows + Linux + Docker)
- Afeta qualquer script shell (`.sh`)
- Não está relacionado a dependências ou permissões

---

## 📅 Última atualização

Março 2026