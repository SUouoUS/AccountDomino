"""DB 를 초기화하고 기본 시나리오(가상 데이터)를 적재한다.

사용법: python scripts/init_db.py [--scenario s1|s2|s3] [--count 4~20]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from accountdomino import auth, config, db  # noqa: E402
from accountdomino.scenarios import SCENARIOS, build_scenario  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="AccountDomino DB 초기화")
    parser.add_argument("--scenario", default="s1", choices=list(SCENARIOS))
    parser.add_argument("--count", type=int, default=config.DEFAULT_ACCOUNT_COUNT,
                        choices=range(config.MIN_ACCOUNT_COUNT, config.MAX_ACCOUNT_COUNT + 1), metavar="4~20")
    args = parser.parse_args()

    conn = db.connect()
    db.init_schema(conn, reset=True)
    sc = SCENARIOS[args.scenario]
    profiles = build_scenario(args.scenario, args.count)
    for profile in config.PROFILES:
        auth.save_accounts(conn, profile, [auth.AccountSetting(**a) for a in profiles[profile]])
    conn.close()
    print(f"DB 초기화 완료: {config.db_path()}")
    print(f"기본 시나리오 적재: {sc['title']} (계정 {args.count}개)")


if __name__ == "__main__":
    main()
