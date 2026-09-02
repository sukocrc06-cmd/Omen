"""
notify.py
----------
Sinyal DEĞİŞTİĞİNDE (ör. BEKLE -> AL, ya da AL -> SAT) Telegram ve/veya e-posta
ile bildirim gönderir. Sinyal her çalıştırmada aynıysa (henüz değişmediyse)
tekrar tekrar bildirim GÖNDERMEZ - son bildirilen durumu bir dosyada saklar.

Bu script tek başına periyodik ÇALIŞMAZ; Windows Görev Zamanlayıcı (Task
Scheduler) ile örn. her saat başı çalıştırılması gerekir (bkz. README'deki
kurulum adımları).

Kurulum (Telegram):
1) Telegram'da "BotFather" ile konuş, /newbot komutuyla yeni bir bot oluştur.
   Sana bir "bot token" verecek (örn. 123456:ABC-DEF...).
2) Oluşturduğun bota Telegram'dan bir mesaj gönder (örn. "merhaba").
3) Tarayıcıda şu adresi aç (TOKEN'ı kendi tokenınla değiştir):
   https://api.telegram.org/botTOKEN/getUpdates
   Dönen JSON içinde "chat":{"id": 123456789} şeklinde bir sayı bulacaksın -
   bu senin chat_id'in.
4) notify_config.json dosyasına bot_token ve chat_id'i yaz (bkz. örnek dosya).

Kurulum (E-posta, opsiyonel):
- Gmail kullanıyorsan normal şifren ÇALIŞMAZ; bir "Uygulama Şifresi" (App
  Password) oluşturman gerekir: Google Hesabı -> Güvenlik -> 2 Adımlı
  Doğrulama (açık olmalı) -> Uygulama Şifreleri.

Kullanım:
    python notify.py --ticker THYAO.IS --interval 1h --config notify_config.json
    python notify.py --ticker THYAO.IS --interval 1h --config notify_config.json --params-file en_iyi_parametreler.json
    python notify.py --ticker THYAO.IS --interval 1h --config notify_config.json --test    # her durumda bildirim gönder (bağlantıyı test etmek için)

    # Birden fazla hisseyi TEK çalıştırmada takip et (her biri kendi durumunu
    # ayrı dosyada tutar, sinyali değişen HER hisse için ayrı bildirim gider):
    python notify.py --tickers "THYAO.IS,ASELS.IS,SISE.IS,KCHOL.IS,BIMAS.IS" --interval 1h \
        --config notify_config.json --params-file en_iyi_parametreler_orta.json
"""

from __future__ import annotations
import argparse
import json
import os
import smtplib
import sys
from email.mime.text import MIMEText

import requests

from data_fetcher import fetch_ohlcv, normalize_interval, default_trailing_atr_mult
from signal_engine import compute_signals, latest_recommendation

STATE_FILE_TEMPLATE = "son_sinyal_{ticker}_{interval}.json"


def load_config(path: str) -> dict:
    if not os.path.exists(path):
        print(f"HATA: Config dosyası bulunamadı: {path}\n"
              f"Örnek için notify_config.example.json dosyasına bakıp bir kopyasını "
              f"'{path}' adıyla kaydet ve kendi bilgilerini gir.")
        sys.exit(1)
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_state(path: str) -> dict | None:
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_state(path: str, state: dict):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def send_telegram(bot_token: str, chat_id: str, text: str) -> bool:
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    try:
        resp = requests.post(url, data={"chat_id": chat_id, "text": text}, timeout=15)
        if resp.status_code == 200:
            return True
        print(f"Telegram HATA ({resp.status_code}): {resp.text}")
        return False
    except Exception as e:
        print(f"Telegram bağlantı hatası: {e}")
        return False


def send_email(cfg: dict, subject: str, body: str) -> bool:
    try:
        msg = MIMEText(body, "plain", "utf-8")
        msg["Subject"] = subject
        msg["From"] = cfg["username"]
        msg["To"] = cfg["to"]
        with smtplib.SMTP(cfg["smtp_server"], cfg.get("smtp_port", 587)) as server:
            server.starttls()
            server.login(cfg["username"], cfg["password"])
            server.sendmail(cfg["username"], [cfg["to"]], msg.as_string())
        return True
    except Exception as e:
        print(f"E-posta gönderim hatası: {e}")
        return False


def build_message(ticker: str, interval: str, rec: dict) -> tuple[str, str]:
    subject = f"[Finans Motoru] {ticker} ({interval}) -> {rec['signal']}"
    body = (
        f"Hisse: {ticker}\n"
        f"Zaman aralığı: {interval}\n"
        f"Tarih/Saat: {rec['datetime']}\n"
        f"Sinyal: {rec['signal']}\n"
        f"Fiyat: {rec['close']}\n"
        f"Skor (-1..1): {rec['score']}\n"
        f"Güven: %{rec['confidence_pct']}\n"
        f"RSI: {rec['rsi']}\n\n"
        f"NOT: {rec['note']}"
    )
    return subject, body


def parse_args():
    p = argparse.ArgumentParser(description="Sinyal değişiminde Telegram/e-posta bildirimi gönder")
    p.add_argument("--ticker", type=str, default="THYAO.IS",
                    help="Tek hisse (--tickers verilmezse kullanılır)")
    p.add_argument("--tickers", type=str, default=None,
                    help="Virgülle ayrılmış birden fazla sembol, ör: 'THYAO.IS,ASELS.IS,SISE.IS' "
                         "- her biri ayrı ayrı takip edilir, sinyali değişen HER hisse için ayrı "
                         "bildirim gönderilir (verilirse --ticker yok sayılır)")
    p.add_argument("--interval", type=str, default="1h")
    p.add_argument("--config", type=str, default="notify_config.json")
    p.add_argument("--params-file", type=str, default=None)
    p.add_argument("--state-dir", type=str, default=".")
    p.add_argument("--test", action="store_true", help="Sinyal değişmemiş olsa bile her seferinde bildirim gönder")
    return p.parse_args()


def process_ticker(ticker: str, interval: str, cfg: dict, params: dict,
                    state_dir: str, force: bool) -> None:
    print(f"\nVeri çekiliyor: {ticker} / {interval} ...")
    try:
        df = fetch_ohlcv(ticker, interval)
    except Exception as e:
        print(f"HATA: Veri çekilemedi ({e})")
        return

    ind_cfg = {k: params[k] for k in ("ema_fast", "ema_slow", "ema_trend", "rsi_len") if k in params}
    signals_df = compute_signals(
        df, cfg=ind_cfg or None,
        buy_th=params.get("buy_th", 0.30), sell_th=params.get("sell_th", -0.30),
        strong_th=params.get("strong_th", 0.60),
    )
    rec = latest_recommendation(signals_df)
    print(f"{ticker}: güncel sinyal {rec['signal']}  (skor={rec['score']}, güven=%{rec['confidence_pct']})")

    state_path = os.path.join(state_dir, STATE_FILE_TEMPLATE.format(
        ticker=ticker.replace(".", "_"), interval=interval))
    prev_state = load_state(state_path)
    changed = force or (prev_state is None) or (prev_state.get("signal") != rec["signal"])

    if not changed:
        print(f"{ticker}: sinyal önceki bildirimden bu yana değişmedi -> bildirim gönderilmiyor.")
        return

    subject, body = build_message(ticker, interval, rec)

    sent_any = False
    tg_cfg = cfg.get("telegram", {})
    if tg_cfg.get("enabled") and tg_cfg.get("bot_token") and tg_cfg.get("chat_id"):
        ok = send_telegram(tg_cfg["bot_token"], tg_cfg["chat_id"], body)
        print(f"{ticker}: Telegram bildirimi gönderildi." if ok else f"{ticker}: Telegram bildirimi GÖNDERİLEMEDİ.")
        sent_any = sent_any or ok

    email_cfg = cfg.get("email", {})
    if email_cfg.get("enabled"):
        ok = send_email(email_cfg, subject, body)
        print(f"{ticker}: E-posta gönderildi." if ok else f"{ticker}: E-posta GÖNDERİLEMEDİ.")
        sent_any = sent_any or ok

    if not sent_any:
        print(f"{ticker}: UYARI: Ne Telegram ne e-posta gönderilebildi (ya devre dışı ya da hata oluştu). "
              "notify_config.json içindeki ayarları kontrol edin.")

    save_state(state_path, {"signal": rec["signal"], "datetime": rec["datetime"]})


def main():
    args = parse_args()
    interval = normalize_interval(args.interval)
    cfg = load_config(args.config)

    params = {}
    if args.params_file and os.path.exists(args.params_file):
        with open(args.params_file, "r", encoding="utf-8") as f:
            params = json.load(f)

    tickers = [t.strip() for t in args.tickers.split(",") if t.strip()] if args.tickers else [args.ticker]

    for ticker in tickers:
        process_ticker(ticker, interval, cfg, params, args.state_dir, args.test)


if __name__ == "__main__":
    main()
