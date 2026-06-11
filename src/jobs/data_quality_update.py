from src.platform.data_quality import refresh_data_quality_report


def main() -> None:
    report = refresh_data_quality_report()
    print(f"Data quality checks saved: {len(report)} rows")
    if not report.empty:
        print(report[["check_name", "severity", "asset_group", "message"]].to_string(index=False))


if __name__ == "__main__":
    main()

