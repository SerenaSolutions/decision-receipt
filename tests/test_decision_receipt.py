# -*- coding: utf-8 -*-
"""Bateria permanente da Action decision-receipt.
Se o veredito trivalente quebrar, este teste falha publicamente."""
import json, os, subprocess, sys, pytest

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENGINE = os.path.join(HERE, "decision_receipt.py")

def decide(payload, prev=None, family="1"):
    d = "/tmp/zqea_test_decision.json"
    json.dump(payload, open(d, "w"))
    cmd = [sys.executable, ENGINE, "--decision", d, "--family", family]
    if prev: cmd += ["--prev", prev]
    r = subprocess.run(cmd, capture_output=True, text=True)
    out = [l for l in r.stdout.splitlines() if l.startswith("VEREDITO")][0]
    verdict = out.split(":")[1].split("|")[0].strip()
    return verdict, r

def write_receipt(payload, path, seal=None):
    payload["selo_sha3_256"] = seal or "0" * 64
    json.dump(payload, open(path, "w"))

def test_confirmado_com_margem():
    v, _ = decide({"metric": 0.99, "threshold": 0.90, "shots": 2048, "epsilon": 0.05})
    assert v == "1"

def test_refutado_com_margem():
    v, _ = decide({"metric": 0.40, "threshold": 0.90, "shots": 2048, "epsilon": 0.05})
    assert v == "0"

def test_dentro_da_banda_recusa():
    v, _ = decide({"metric": 0.905, "threshold": 0.90, "shots": 64, "epsilon": 0.05})
    assert v == "REFUSED"  # 64 shots: banda ~0.236; diferenca 0.005 e ruido honesto

def test_familha_bonferroni_exige_mais_shots():
    # com 2048 shots a decisao unica passa (banda 0.027 < diff 0.05);
    # na familia 50 a banda alarga pra 0.082 e a MESMA evidencia recusa
    # MESMA evidencia (2048 shots, diff 0.05): familia 1 confirma (banda 0.027);
    # familia 2000 alarga a banda pra 0.051 e a evidencia ja nao basta
    v1, _ = decide({"metric": 0.95, "threshold": 0.90, "shots": 2048, "epsilon": 0.05}, family="1")
    v2000, _ = decide({"metric": 0.95, "threshold": 0.90, "shots": 2048, "epsilon": 0.05}, family="2000")
    assert v1 == "1" and v2000 == "REFUSED"

def test_epsilon_degenerado_recusa_tudo():
    # epsilon >= family => alpha >= 1: nenhuma confianca declaravel
    v, _ = decide({"metric": 0.99, "threshold": 0.90, "shots": 4096, "epsilon": 1.0}, family="1")
    assert v == "REFUSED"

def test_genese_sem_prev():
    v, r = decide({"metric": 0.99, "threshold": 0.90, "shots": 1024, "epsilon": 0.05})
    rec = json.load(open("/tmp/zqea_test_decision.receipt.json"))
    assert v == "1" and rec["previous_seal"] == "genesis"

def test_evidencia_invalida_recusa():
    v, _ = decide({"metric": 1.7, "threshold": 0.90, "shots": 1024, "epsilon": 0.05})
    assert v == "REFUSED"

def test_prev_adulterado_quebra_cadeia():
    prev = "/tmp/zqea_test_prev.json"
    write_receipt({"metric": 0.9, "threshold": 0.9, "shots": 100, "verdict": "1"}, prev, seal="falso")
    v, r = decide({"metric": 0.99, "threshold": 0.90, "shots": 1024, "epsilon": 0.05}, prev=prev)
    assert v == "REFUSED" and "CHAIN_BROKEN" in r.stdout

def test_prev_integro_encadeia():
    prev = "/tmp/zqea_test_prev2.json"
    # gera um recibo verdadeiro primeiro
    decide({"metric": 0.99, "threshold": 0.90, "shots": 1024, "epsilon": 0.05})
    import shutil; shutil.copy("/tmp/zqea_test_decision.receipt.json", prev)
    v, r = decide({"metric": 0.99, "threshold": 0.90, "shots": 1024, "epsilon": 0.05}, prev=prev)
    rec = json.load(open("/tmp/zqea_test_decision.receipt.json"))
    assert v == "1" and rec["previous_seal"] != "genesis"
