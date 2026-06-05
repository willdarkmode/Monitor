import os
import re
import json
import logging
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta

import requests
import urllib3
from bs4 import BeautifulSoup
from dateutil.easter import easter
from dotenv import load_dotenv

load_dotenv()
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


def env_float(nome: str, padrao: float) -> float:
    try:
        return float(os.getenv(nome, padrao))
    except ValueError:
        return padrao


SANKHYA_CRED = {
    "USUARIO": os.getenv("SANKHYA_USUARIO", ""),
    "SENHA": os.getenv("SANKHYA_SENHA", ""),
    "BASE_URL": os.getenv("SANKHYA_BASE_URL", ""),
    "SESSAO_ESTOQUE": os.getenv("SANKHYA_SESSAO_ESTOQUE", ""),
    "SESSAO_FATURAMENTO": os.getenv("SANKHYA_SESSAO_FATURAMENTO", ""),
}

METAS = {
    "META_BASE": env_float("META_BASE", 3750000.00),
    "SUPER_META": env_float("SUPER_META", 4000000.00),
}


class FeriadosBrasil:
    @staticmethod
    def eh_feriado(data):
        if isinstance(data, datetime):
            data = data.date()
        ano = data.year
        feriados_fixos = {
            (1, 1), (4, 21), (5, 1), (9, 7), (10, 12),
            (11, 2), (11, 15), (11, 20), (12, 25)
        }
        pascoa = easter(ano)
        feriados_moveis = {
            pascoa - timedelta(days=48),
            pascoa - timedelta(days=47),
            pascoa - timedelta(days=2),
            pascoa,
            pascoa + timedelta(days=60),
        }
        return (data.month, data.day) in feriados_fixos or data in feriados_moveis


class SankhyaReporter:
    def __init__(self):
        self.logger = logging.getLogger("SankhyaDashboard")
        self.logger.setLevel(logging.INFO)
        if not self.logger.hasHandlers():
            handler = logging.StreamHandler()
            formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
            handler.setFormatter(formatter)
            self.logger.addHandler(handler)

        self.cookies = None
        self.login_em = None
        self.sessao_ttl_segundos = int(os.getenv("SANKHYA_SESSAO_TTL_SEGUNDOS", "900"))

    def fazer_login(self):
        if not all([SANKHYA_CRED["USUARIO"], SANKHYA_CRED["SENHA"], SANKHYA_CRED["BASE_URL"]]):
            self.logger.warning("Credenciais Sankhya incompletas no .env")
            return None

        login_url = f'{SANKHYA_CRED["BASE_URL"]}/service.sbr?serviceName=MobileLoginSP.login'
        data = f"""
        <serviceRequest serviceName="MobileLoginSP.login">
            <requestBody>
                <NOMUSU>{SANKHYA_CRED["USUARIO"]}</NOMUSU>
                <INTERNO>{SANKHYA_CRED["SENHA"]}</INTERNO>
            </requestBody>
        </serviceRequest>
        """
        try:
            response = requests.post(
                login_url,
                data=data,
                headers={"Content-Type": "text/xml; charset=UTF-8"},
                timeout=45,
                verify=False,
            )
            if response.status_code == 200 and "JSESSIONID" in response.cookies:
                return response.cookies
            self.logger.error("Login Sankhya falhou. Status: %s", response.status_code)
        except Exception as exc:
            self.logger.exception("Erro no login Sankhya: %s", exc)
        return None
    
    def sessao_valida(self):
        if not self.cookies or not self.login_em:
            return False

        idade = (datetime.now() - self.login_em).total_seconds()
        return idade < self.sessao_ttl_segundos

    def limpar_sessao(self):
        self.cookies = None
        self.login_em = None

    def obter_cookies(self, forcar_login=False):
        if not forcar_login and self.sessao_valida():
            self.logger.info("Reutilizando sessão Sankhya existente")
            return self.cookies

        cookies = self.fazer_login()

        if cookies:
            self.cookies = cookies
            self.login_em = datetime.now()

        return cookies    

    def calcular_periodo(self):
        hoje = datetime.now()
        if hoje.day >= 5:
            inicio = hoje.replace(day=5)
            fim = (hoje.replace(day=1) + timedelta(days=32)).replace(day=4)
        else:
            inicio = (hoje.replace(day=1) - timedelta(days=1)).replace(day=5)
            fim = hoje.replace(day=4)
        return inicio.strftime("%d/%m/%Y"), fim.strftime("%d/%m/%Y")

    def buscar_dados(self, cookies, tipo):
        endpoint = f'{SANKHYA_CRED["BASE_URL"]}/service.sbr'
        sessao = SANKHYA_CRED["SESSAO_ESTOQUE" if tipo == "estoque" else "SESSAO_FATURAMENTO"]
        params = {
            "serviceName": "DynaGadgetBuilderSP.resolveGadgetLevel",
            "mgeSession": sessao,
        }

        if tipo == "faturamento":
            inicio, fim = self.calcular_periodo()
            data = f"""
            <serviceRequest serviceName="DynaGadgetBuilderSP.resolveGadgetLevel">
                <requestBody>
                    <parameters NUGADGET="456" LEVEL-ID="lvl_j5217d" LEVEL-PATH="lvl_j5217d">
                        <prompt-parameters>
                            <parameter id="PERIODO.INI">{inicio}</parameter>
                            <parameter id="PERIODO.FIN">{fim}</parameter>
                            <parameter id="CODEMP">'1', '2'</parameter>
                        </prompt-parameters>
                    </parameters>
                </requestBody>
            </serviceRequest>
            """
        else:
            data = """
            <serviceRequest serviceName="DynaGadgetBuilderSP.resolveGadgetLevel">
                <requestBody>
                    <parameters NUGADGET="206" LEVEL-ID="lvl_a7yoata" LEVEL-PATH="lvl_a7yoata"/>
                </requestBody>
            </serviceRequest>
            """

        try:
            response = requests.post(endpoint, params=params, data=data, cookies=cookies, timeout=60, verify=False)
            response.raise_for_status()
            return self.parse_response(response.text, tipo)
        except Exception as exc:
            self.logger.exception("Erro ao buscar %s: %s", tipo, exc)
            return None
            
    def ler_float_xml(self, row, campo):
        valor = row.findtext(campo)

        if not valor:
            return 0.0

        valor = str(valor).strip()
        valor = valor.replace("R$", "").replace(" ", "")

        if "," in valor:
            valor = valor.replace(".", "").replace(",", ".")

        try:
            return float(valor)
        except:
            return 0.0        

    def parse_response(self, xml_data, tipo):
        mapeamento = {
            "estoque": {
                "svl_3SX": "Estoque Total",
                "svl_0VL": "Novos P&R",
                "svl_07T": "Novos RGA",
                "svl_08T": "Usados P&R",
                "svl_08U": "Usados RGA",
                "svl_08N": "Especiais",
                "svl_0IG": "Separados",
            },
            "faturamento": {
                "svl_j7r98z": "Faturado + Previsto",
                "svl_1BJ": "Devoluções",
                "svl_j5217e": "Total Faturado",
                "svl_j5217g": "Total Previsto",
                "svl_0Q5": "Grande Chance",
            },
        }
        try:
            root = ET.fromstring(xml_data)
            dados = {}

            for sv in root.findall(".//simple-value"):
                id_atributo = sv.attrib.get("id")
                valor_html = sv.findtext("value-field") or ""
                valor_txt = BeautifulSoup(valor_html, "html.parser").text.strip()

                if id_atributo in mapeamento[tipo]:
                    descricao = mapeamento[tipo][id_atributo]
                    valor = re.search(r"R\$\s*([\d.,]+)", valor_txt)
                    dados[descricao] = float(valor.group(1).replace(".", "").replace(",", ".")) if valor else 0.0

            if tipo == "faturamento":
                vendedores = []

                for row in root.findall(".//data-provider/row"):
                    apelido = row.findtext("APELIDO")

                    if apelido and apelido != "<SEM VENDEDOR>":
                        vend = self.ler_float_xml(row, "VEND")
                        opor = self.ler_float_xml(row, "OPOR")
                        meta = self.ler_float_xml(row, "META")
                        faltante = self.ler_float_xml(row, "FALTANTE")
                        atingimento = self.ler_float_xml(row, "ATINGIMENTO")

                        total = vend + opor

                        if total > 0 or meta > 0:
                            vendedores.append({
                                "Vendedor": apelido,
                                "Faturado": vend,
                                "Previsto": opor,
                                "Total": total,
                                "Meta": meta,
                                "Faltante": faltante,
                                "Atingimento": atingimento
                            })

                vendedores.sort(key=lambda x: x["Total"], reverse=True)
                dados["Vendedores"] = vendedores

            return dados
        except Exception as exc:
            self.logger.exception("Erro ao parsear %s: %s", tipo, exc)
            return None

    def gerar_dashboard(self):
        cookies = self.obter_cookies()
        if not cookies:
            return None

        estoque = self.buscar_dados(cookies, "estoque")
        faturamento = self.buscar_dados(cookies, "faturamento")

        if estoque is None or faturamento is None:
            self.logger.warning("Sessão Sankhya pode ter expirado. Tentando novo login.")

            self.limpar_sessao()
            cookies = self.obter_cookies(forcar_login=True)

            if not cookies:
                return None

            estoque = self.buscar_dados(cookies, "estoque") or {}
            faturamento = self.buscar_dados(cookies, "faturamento") or {}
        else:
            estoque = estoque or {}
            faturamento = faturamento or {}

        inicio, fim = self.calcular_periodo()

        return {
            "fonte": "sankhya",
            "atualizado_em": datetime.now().isoformat(),
            "periodo": {"inicio": inicio, "fim": fim},
            "metas": METAS,
            "estoque": estoque,
            "faturamento": faturamento,
        }


def gerar_mock():
    agora = datetime.now()
    realizado = 2987500.0
    return {
        "fonte": "mock",
        "atualizado_em": agora.isoformat(),
        "periodo": {"inicio": "05/06/2026", "fim": "04/07/2026"},
        "metas": METAS,
        "estoque": {
            "Estoque Total": 2145000,
            "Novos P&R": 690000,
            "Novos RGA": 360000,
            "Usados P&R": 420000,
            "Usados RGA": 290000,
            "Especiais": 185000,
            "Separados": 200000,
        },
        "faturamento": {
            "Faturado + Previsto": realizado,
            "Devoluções": 82000,
            "Total Faturado": 2380000,
            "Total Previsto": 607500,
            "Grande Chance": 410000,
            "Vendedores": [
                {"Vendedor": "Ana Paula", "Faturado": 640000, "Previsto": 180000, "Total": 820000},
                {"Vendedor": "Carlos", "Faturado": 580000, "Previsto": 130000, "Total": 710000},
                {"Vendedor": "João", "Faturado": 470000, "Previsto": 120000, "Total": 590000},
                {"Vendedor": "Mariana", "Faturado": 380000, "Previsto": 100000, "Total": 480000},
                {"Vendedor": "Rafael", "Faturado": 310000, "Previsto": 65000, "Total": 375000},
            ],
        },
    }
