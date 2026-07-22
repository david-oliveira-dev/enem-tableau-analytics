"""Download dos microdados do ENEM a partir do portal do INEP.

Usa APENAS a biblioteca padrão de propósito: é a etapa mais demorada do pipeline
(meia hora de download), então ela não deve depender da venv estar montada. Assim
dá para disparar o download com o Python do sistema enquanto o resto instala.

Uso:
    python src/download.py --anos 2023 2024
    python src/download.py --anos 2023 --insecure   # ver nota sobre TLS abaixo

NOTA SOBRE TLS  (leia antes de sair desligando verificação)
-----------------------------------------------------------
`download.inep.gov.br` responde com a CADEIA INCOMPLETA: manda só o certificado
folha (`*.inep.gov.br`) e omite o intermediário que o assinou
(`RNP ICPEdu GR46 OV TLS CA 2025`). Resultado: qualquer cliente que não tenha o
intermediário em cache falha com "unable to get local issuer certificate" — curl,
requests, urllib, todos. Navegador funciona porque ele busca o intermediário sozinho
pela extensão AIA do certificado.

Isso é um erro de configuração do servidor, NÃO uma conexão insegura. A correção
certa é fornecer o intermediário, e não desligar a verificação: o intermediário está
versionado em `certs/` e encadeia até a GlobalSign Root R46, que já é confiável no
trust store do sistema. A assinatura continua sendo checada de ponta a ponta.

A flag --insecure existe só como último recurso (rede com proxy de inspeção TLS) e
grita quando usada.
"""

from __future__ import annotations

import argparse
import hashlib
import shutil
import ssl
import sys
import time
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config import DATA_INTERIM, DATA_RAW, MICRODADOS_URL, TAMANHO_ESPERADO_ZIP

# O host do INEP rejeita user-agents vazios em algumas rotas de CDN.
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; enem-tableau-analytics/1.0)"}

# Intermediário faltante na cadeia servida pelo INEP (ver docstring do módulo).
# Baixado da URL de AIA do próprio certificado folha:
#   http://secure.globalsign.com/cacert/rnpicpedugr46ovtlsca2025.crt
CERT_INTERMEDIARIO = Path(__file__).resolve().parent.parent / "certs" / (
    "rnp_icpedu_gr46_ov_tls_ca_2025.pem"
)
CERT_INTERMEDIARIO_SHA256 = (
    "e10747d4da7bab09cba9952f019d3534cb9fba070bf13d8791b1699cd2ff59dd"
)

MAX_TENTATIVAS = 5  # o host do INEP derruba conexões longas com alguma frequência


def _contexto_ssl(inseguro: bool) -> ssl.SSLContext:
    """Monta o contexto TLS: trust store do sistema + intermediário da RNP."""
    ctx = ssl.create_default_context()

    if inseguro:
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        return ctx

    if CERT_INTERMEDIARIO.exists():
        # Impressão digital sobre o DER, que é a definição padrão de fingerprint de
        # certificado — bate com `openssl x509 -fingerprint -sha256`. Hashear os bytes
        # do PEM daria outro valor e não seria comparável com nenhuma outra ferramenta.
        der = ssl.PEM_cert_to_DER_cert(CERT_INTERMEDIARIO.read_text())
        impressao = hashlib.sha256(der).hexdigest()
        # Conferir a impressão evita usar um intermediário trocado no repositório.
        # (Mesmo trocado ele não passaria na validação da cadeia — isso aqui é só
        # para falhar com mensagem clara em vez de erro críptico de TLS.)
        if impressao != CERT_INTERMEDIARIO_SHA256:
            print(
                f"  ⚠  {CERT_INTERMEDIARIO.name} tem sha256 inesperado ({impressao}). "
                "Se o INEP renovou o certificado, atualize CERT_INTERMEDIARIO_SHA256."
            )
        ctx.load_verify_locations(cafile=str(CERT_INTERMEDIARIO))
    else:
        print(
            f"  ⚠  {CERT_INTERMEDIARIO} não encontrado. A verificação TLS provavelmente "
            "vai falhar — veja a nota sobre TLS no topo deste arquivo."
        )

    return ctx


def _humano(n: float) -> str:
    for unidade in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.1f} {unidade}"
        n /= 1024
    return f"{n:.1f} TB"


def baixar(ano: int, inseguro: bool = False, forcar: bool = False) -> Path:
    """Baixa o .zip de uma edição. Reaproveita o arquivo se já estiver íntegro."""
    url = MICRODADOS_URL.format(ano=ano)
    destino = DATA_RAW / f"microdados_enem_{ano}.zip"
    esperado = TAMANHO_ESPERADO_ZIP.get(ano)

    if destino.exists() and not forcar:
        tamanho = destino.stat().st_size
        # Só reaproveita se o tamanho bater — um .zip truncado de download anterior
        # passaria despercebido e estouraria lá na frente, no unzip.
        if esperado is None or tamanho == esperado:
            print(f"[{ano}] já baixado ({_humano(tamanho)}), pulando.")
            return destino
        print(f"[{ano}] arquivo local incompleto ({_humano(tamanho)}), rebaixando.")

    ctx = _contexto_ssl(inseguro)
    if inseguro:
        print("  ⚠  VERIFICAÇÃO DE CERTIFICADO DESLIGADA (--insecure).")

    parcial = destino.with_suffix(".zip.part")
    inicio = time.time()
    print(f"[{ano}] baixando {url}")

    # O host do INEP derruba conexão longa com alguma frequência e o arquivo tem
    # centenas de MB. Como ele aceita requisições Range (responde 206), retomamos do
    # ponto onde parou em vez de recomeçar meia hora de download do zero.
    for tentativa in range(1, MAX_TENTATIVAS + 1):
        ja_baixado = parcial.stat().st_size if parcial.exists() else 0
        cabecalhos = dict(HEADERS)
        if ja_baixado:
            cabecalhos["Range"] = f"bytes={ja_baixado}-"
            print(f"[{ano}] retomando de {_humano(ja_baixado)}")

        try:
            req = urllib.request.Request(url, headers=cabecalhos)
            with urllib.request.urlopen(req, context=ctx, timeout=60) as resp:
                # Se pedimos Range e o servidor ignorou (200 em vez de 206), ele vai
                # mandar o arquivo inteiro — nesse caso reescrevemos do zero, senão
                # concatenaríamos bytes duplicados e corromperíamos o zip.
                retomando = ja_baixado > 0 and resp.status == 206
                if ja_baixado and not retomando:
                    print(f"[{ano}] servidor ignorou Range; recomeçando do zero.")
                    ja_baixado = 0

                restante = int(resp.headers.get("Content-Length", 0))
                total = ja_baixado + restante
                print(f"[{ano}] tamanho total: {_humano(total)}")

                baixado = ja_baixado
                ultimo_log = 0.0
                with open(parcial, "ab" if retomando else "wb") as fh:
                    while bloco := resp.read(1024 * 512):
                        fh.write(bloco)
                        baixado += len(bloco)
                        agora = time.time()
                        if agora - ultimo_log >= 10:  # log a cada 10s, não a cada bloco
                            pct = 100 * baixado / total if total else 0
                            vel = (baixado - ja_baixado) / max(agora - inicio, 1e-6)
                            print(
                                f"[{ano}] {pct:5.1f}%  {_humano(baixado)}"
                                f"  ({_humano(vel)}/s)",
                                flush=True,
                            )
                            ultimo_log = agora
            break  # download completo

        except urllib.error.URLError as exc:
            if isinstance(exc.reason, ssl.SSLCertVerificationError):
                # Erro de configuração, não de rede: repetir não resolve.
                raise SystemExit(
                    "Falha na verificação do certificado TLS de download.inep.gov.br.\n"
                    f"Confira se {CERT_INTERMEDIARIO.name} existe em certs/. Se o INEP "
                    "renovou o certificado, rebaixe o intermediário com:\n"
                    "  openssl s_client -connect download.inep.gov.br:443 </dev/null \\\n"
                    "    | openssl x509 -noout -text | grep -A2 'Authority Information'\n"
                    "e salve a URL de 'CA Issuers' em certs/ (convertendo DER→PEM).\n"
                    "Só use --insecure se você entende e aceita o risco."
                ) from exc
            if tentativa == MAX_TENTATIVAS:
                raise
            espera = 2 ** tentativa
            print(f"[{ano}] falha ({exc.reason}); tentativa {tentativa}/"
                  f"{MAX_TENTATIVAS}, aguardando {espera}s...", flush=True)
            time.sleep(espera)
        except (ConnectionResetError, TimeoutError) as exc:
            if tentativa == MAX_TENTATIVAS:
                raise
            espera = 2 ** tentativa
            print(f"[{ano}] conexão caiu ({type(exc).__name__}); tentativa "
                  f"{tentativa}/{MAX_TENTATIVAS}, aguardando {espera}s...", flush=True)
            time.sleep(espera)

    shutil.move(parcial, destino)

    tamanho = destino.stat().st_size
    if esperado is not None and tamanho != esperado:
        # Não apagamos o arquivo: quem decide descartar dado é o usuário.
        print(
            f"  ⚠  [{ano}] tamanho {tamanho} difere do esperado {esperado}. "
            "Pode ser reedição do INEP ou download truncado — confira antes de usar."
        )

    print(
        f"[{ano}] concluído em {(time.time() - inicio) / 60:.1f} min "
        f"({_humano(tamanho)}) → {destino}"
    )
    print(f"[{ano}] sha256: {sha256(destino)}")
    return destino


def sha256(caminho: Path, blocos: int = 1024 * 1024) -> str:
    h = hashlib.sha256()
    with open(caminho, "rb") as fh:
        while bloco := fh.read(blocos):
            h.update(bloco)
    return h.hexdigest()


def extrair_csv(ano: int) -> Path:
    """Extrai do .zip somente o CSV de participantes.

    O zip traz ~500 MB de PDFs de provas, gabaritos e inputs de SAS/SPSS que não
    interessam aqui. Extrair o pacote inteiro num HD mecânico é caro e ocupa disco à
    toa, então localizamos o CSV pelo padrão do nome e extraímos só ele.
    """
    zip_path = DATA_RAW / f"microdados_enem_{ano}.zip"
    if not zip_path.exists():
        raise FileNotFoundError(f"{zip_path} não existe — rode o download primeiro.")

    destino = DATA_INTERIM / f"MICRODADOS_ENEM_{ano}.csv"
    if destino.exists():
        print(f"[{ano}] CSV já extraído ({_humano(destino.stat().st_size)}).")
        return destino

    with zipfile.ZipFile(zip_path) as zf:
        candidatos = [
            n for n in zf.namelist()
            if n.upper().endswith(".CSV") and "MICRODADOS_ENEM" in n.upper()
        ]
        if not candidatos:
            # Fallback: o maior .csv do pacote é sempre o de participantes.
            csvs = [n for n in zf.namelist() if n.upper().endswith(".CSV")]
            if not csvs:
                raise RuntimeError(f"Nenhum CSV encontrado em {zip_path}")
            candidatos = [max(csvs, key=lambda n: zf.getinfo(n).file_size)]

        alvo = max(candidatos, key=lambda n: zf.getinfo(n).file_size)
        info = zf.getinfo(alvo)
        print(f"[{ano}] extraindo {alvo} ({_humano(info.file_size)})...")

        with zf.open(alvo) as origem, open(destino, "wb") as saida:
            shutil.copyfileobj(origem, saida, length=1024 * 1024)

    print(f"[{ano}] CSV pronto → {destino}")
    return destino


def listar_conteudo(ano: int, limite: int = 40) -> None:
    """Imprime o conteúdo do zip — útil para localizar o dicionário de variáveis."""
    zip_path = DATA_RAW / f"microdados_enem_{ano}.zip"
    with zipfile.ZipFile(zip_path) as zf:
        itens = sorted(zf.infolist(), key=lambda i: -i.file_size)
        for info in itens[:limite]:
            print(f"  {_humano(info.file_size):>10}  {info.filename}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--anos", nargs="+", type=int, default=[2023, 2024])
    ap.add_argument("--insecure", action="store_true", help="não verifica o certificado TLS")
    ap.add_argument("--forcar", action="store_true", help="rebaixa mesmo se já existir")
    ap.add_argument("--extrair", action="store_true", help="extrai o CSV após baixar")
    ap.add_argument("--listar", action="store_true", help="só lista o conteúdo do zip")
    args = ap.parse_args()

    for ano in args.anos:
        if args.listar:
            listar_conteudo(ano)
            continue
        baixar(ano, inseguro=args.insecure, forcar=args.forcar)
        if args.extrair:
            extrair_csv(ano)


if __name__ == "__main__":
    main()
