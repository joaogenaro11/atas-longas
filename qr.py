"""Imprime um QR code no terminal para uma URL (para abrir no celular).
Uso: python qr.py https://algo.trycloudflare.com
Se a lib 'qrcode' não estiver instalada, sai sem erro."""
import sys

url = sys.argv[1] if len(sys.argv) > 1 else ""
if not url:
    sys.exit(0)
try:
    import qrcode
except Exception:
    sys.exit(0)

q = qrcode.QRCode(border=1)
q.add_data(url)
q.make()
q.print_ascii(invert=True)
