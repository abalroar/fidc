"""Index all saved portfolios and acquire documents serially when --network is explicit."""
from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.documentary_corpus import DocumentaryCorpus, ResourceLimits, load_registered_funds


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    selection = parser.add_mutually_exclusive_group(required=True)
    selection.add_argument("--all", action="store_true", help="Todos os CNPJs únicos de portfolios.json")
    selection.add_argument("--only-cnpj", action="append", default=[])
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--source-root", action="append", type=Path, default=[])
    parser.add_argument("--resume", action="store_true", help="Reutiliza textos íntegros e preserva inventários anteriores")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--network", action="store_true", help="Adquire PDFs faltantes, um arquivo por vez")
    mode.add_argument("--local-only", action="store_true", help="Somente acervo existente (padrão)")
    parser.add_argument("--max-download-gb", type=float, default=2)
    parser.add_argument("--disk-floor-gb", type=float, default=10)
    parser.add_argument("--max-document-mb", type=float, default=100)
    parser.add_argument("--network-timeout-seconds", type=int, default=20)
    parser.add_argument("--attempts", type=int, default=2)
    parser.add_argument("--skip-successful-network", action="store_true", help="Reutiliza listagem concluída; ainda tenta PDFs faltantes")
    parser.add_argument("--acquisition-pass", choices=("current", "history", "all"), default="all",
                        help="current cataloga todos e baixa regulamentos/anexos recentes; history retoma documentos adiados; all preserva aquisição integral")
    args = parser.parse_args()
    if min(args.max_download_gb, args.disk_floor_gb, args.max_document_mb) < 0:
        parser.error("Limites de recursos devem ser não negativos")
    if args.network_timeout_seconds < 1 or not 1 <= args.attempts <= 3:
        parser.error("Timeout deve ser positivo; tentativas devem estar entre 1 e 3")
    funds = load_registered_funds(args.root / "portfolios.json")
    selected = sorted(funds) if args.all else list(dict.fromkeys("".join(char for char in cnpj if char.isdigit()) for cnpj in args.only_cnpj))
    limits = ResourceLimits(disk_floor_bytes=int(args.disk_floor_gb * 1024**3), max_download_bytes=int(args.max_download_gb * 1024**3),
                            max_document_bytes=int(args.max_document_mb * 1024**2), network_timeout_seconds=args.network_timeout_seconds,
                            attempts=args.attempts)
    corpus = DocumentaryCorpus(args.root, args.source_root, limits=limits)
    corpus.prepare(selected)
    totals = Counter()
    for index, cnpj in enumerate(selected, 1):
        payload = corpus.refresh(cnpj, network=args.network, resume=args.resume, fund=funds.get(cnpj),
                                 skip_successful_network=args.skip_successful_network, acquisition_pass=args.acquisition_pass)
        totals.update(payload["summary"])
        statuses = Counter(row["parse_status"] for row in payload["documents"])
        print(f"[{index}/{len(selected)}] {cnpj}: {payload['summary']['documents']} documentos; parsing {dict(statuses)}", flush=True)
    print(f"Concluído: {len(selected)} CNPJs; {dict(totals)}; download {corpus.downloaded_bytes} bytes", flush=True)
    print("CNPJs mencionados como investidos permanecem candidatos até validação da fonte primária.", flush=True)


if __name__ == "__main__":
    main()
