# -*- coding: utf-8 -*-
"""Z-QEA DECISION RECEIPT — veredito trivalente com recibo selado para CI.

A regra e declarada ANTES de ler a evidencia (ordem do codigo = ordem do
protocolo). Vereditos: 1 (afirmado com margem), 0 (refutado com margem),
REFUSED (dentro da banda: nao sabe, nao mente).

Banda unilateral Hoeffding com correcao Bonferroni por familia:
    alpha = epsilon / family;  band = sqrt( ln(1/alpha) / (2 * shots) )
GABARITO ANTI-PEEKING: o recibo grava a regra declarada antes do dado.
GABARITO GENESE: sem prev-receipt, o recibo declara previous_seal=genesis
(raiz de cadeia nova, nunca erro silencioso).
GABARITO INTEGRIDADE: recibo anterior adulterado => REFUSED (CHAIN_BROKEN).
"""
import argparse, json, math, os, sys

RULE = ("one-sided Hoeffding: alpha=epsilon/family, "
        "band=sqrt(ln(1/alpha)/(2*shots)); claim metric>=threshold; "
        "metric-threshold>=band => 1; threshold-metric>=band => 0; "
        "senao REFUSED")
CANON_NOTE = ("selo = SHA3-256 sobre json.dumps(payload, sort_keys=True, "
              "ensure_ascii=True, default=str) com selo_sha3_256 removido")

def canonical(payload):
    return json.dumps(payload, sort_keys=True, ensure_ascii=True, default=str)

def sha3_seal(payload):
    import hashlib
    return hashlib.sha3_256(canonical(payload).encode()).hexdigest()

def declared_rule(epsilon, family):
    """Regra selada ANTES do dado: so epsilon e family entram aqui."""
    if family < 1:
        return None, "family deve ser >= 1"
    alpha = epsilon / family if epsilon > 0 else 1.0
    if alpha >= 1.0:
        return None, ("familia %d excede o epsilon %.4g: "
                      "shots nao sustentam a familia Bonferroni" % (family, epsilon))
    return alpha, None

def trivalent(metric, threshold, shots, alpha):
    band = math.sqrt(math.log(1.0 / alpha) / (2.0 * shots))
    if not (0.0 <= metric <= 1.0 and 0.0 <= threshold <= 1.0):
        return "REFUSED", "INVALID_EVIDENCE", band, "metric/threshold fora de [0,1]"
    if metric - threshold >= band:
        return "1", "CONFIRMED_WITH_MARGIN", band, "afirmado acima da banda"
    if threshold - metric >= band:
        return "0", "REFUTED_WITH_MARGIN", band, "refutado abaixo da banda"
    return "REFUSED", "INSIDE_NOISE_BAND", band, (
        "diferenca |%.6g| dentro da banda +-%.6g: a evidencia nao sustenta "
        "resposta binaria" % (abs(metric - threshold), band))

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--decision", required=True)
    p.add_argument("--prev", default=None)
    p.add_argument("--family", type=int, default=1)
    p.add_argument("--sign-from-env", action="store_true")
    a = p.parse_args()

    ev = json.load(open(a.decision))
    epsilon = float(ev.get("epsilon", 0.05))
    metric, threshold = float(ev["metric"]), float(ev["threshold"])
    shots = int(ev.get("shots", 1))
    desc = ev.get("description", a.decision)

    # (1) regra selada antes do dado
    alpha, rule_err = declared_rule(epsilon, a.family)
    prev_seal, prev_verdict = "genesis", None
    if a.prev and os.path.exists(a.prev):
        prev = json.load(open(a.prev))
        prev_payload = {k: v for k, v in prev.items() if k != "selo_sha3_256"}
        if prev.get("selo_sha3_256") != sha3_seal(prev_payload):
            print("::error title=CHAIN_BROKEN::recibo anterior adulterado "
                  "(selo nao reconfere) — recusando encadear")
            verdict, reason, band, why = "REFUSED", "CHAIN_BROKEN", 0.0, "historico invalido"
            emit(a, ev, verdict, reason, band, why, alpha, prev_seal, None, sign=False)
            return 2
        prev_seal, prev_verdict = prev["selo_sha3_256"], prev.get("verdict")
    elif a.prev:
        print("::warning title=GENESIS::prev-receipt informado mas ausente; "
              "selando recibo GENESIS de cadeia nova")

    if rule_err:
        verdict, reason, band, why = "REFUSED", "FAMILY_EXCEEDS_EVIDENCE", 0.0, rule_err
        emit(a, ev, verdict, reason, band, why, None, prev_seal, prev_verdict, sign=a.sign_from_env)
        return 1
    if shots <= 0:
        verdict, reason, band, why = "REFUSED", "INSUFFICIENT_CONFIDENCE", 0.0, "shots <= 0"
        emit(a, ev, verdict, reason, band, why, alpha, prev_seal, prev_verdict, sign=a.sign_from_env)
        return 1
    verdict, reason, band, why = trivalent(metric, threshold, shots, alpha)
    emit(a, ev, verdict, reason, band, why, alpha, prev_seal, prev_verdict, sign=a.sign_from_env)
    return 0 if verdict != "REFUSED" else 1

def emit(a, ev, verdict, reason, band, why, alpha, prev_seal, prev_verdict, sign):
    rec = {
        "modulo": "Z-QEA DECISION RECEIPT",
        "regra": RULE, "forma_canonica": CANON_NOTE,
        "epsilon": ev.get("epsilon", 0.05), "family": a.family,
        "alpha_unilateral": alpha,
        "metric": ev["metric"], "threshold": ev["threshold"],
        "shots": ev.get("shots", 1), "banda": round(band, 6),
        "verdict": verdict, "reason": reason, "why": why,
        "description": ev.get("description", a.decision),
        "previous_seal": prev_seal, "previous_verdict": prev_verdict,
    }
    payload = dict(rec)
    rec["selo_sha3_256"] = sha3_seal(payload)
    sig = None
    if sign:
        key = os.environ.get("ZQEA_SIGNING_KEY", "")
        if key:
            try:
                sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))
                from zqea_pq import sign_receipt
                sig = sign_receipt(rec)
                rec["assinatura_ml_dsa_44"] = sig
            except Exception as e:
                print("::warning title=ASSINATURA::ML-DSA indisponivel (%s); "
                      "recibo selado sem assinatura" % type(e).__name__)
    out = a.decision.replace(".json", "") + ".receipt.json"
    json.dump(rec, open(out, "w"), indent=1, ensure_ascii=True, sort_keys=True)
    gout = os.environ.get("GITHUB_OUTPUT", "/dev/null")
    with open(gout, "a") as f:
        f.write("verdict=%s\n" % verdict)
        f.write("reason=%s\n" % reason)
        f.write("receipt=%s\n" % out)
        f.write("seal=%s\n" % rec["selo_sha3_256"])
    summ = os.environ.get("GITHUB_STEP_SUMMARY")
    if summ:
        with open(summ, "a") as f:
            f.write("\n### Z-QEA Decision Receipt\n\n"
                    "| campo | valor |\n|---|---|\n"
                    "| veredito | **%s** (%s) |\n| banda | +-%.6f |\n"
                    "| shots | %s | familia | %s |\n"
                    "| por que | %s |\n| selo | `%s` |\n"
                    "| encadeado em | `%s` |\n"
                    % (verdict, reason, band, ev.get("shots", 1), a.family,
                       why, rec["selo_sha3_256"][:32], prev_seal[:32]))
    print("VEREDITO:", verdict, "|", reason, "| banda +-%.6f" % band)
    print("  por que:", why)
    print("  recibo:", out, "| selo:", rec["selo_sha3_256"][:32], "| assinatura:", "ML-DSA-44" if sig else "nao")

if __name__ == "__main__":
    sys.exit(main())
