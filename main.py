# Forecasting idea: pull the checkpoint close part-way toward its trailing
# six-hour average and part-way toward its trailing twenty-four-hour average.
# At a four-hour horizon, this price series tends to revert toward its recent
# averages rather than continue its latest move. The pull is deliberately
# small, so a hard one-direction trend can add only a bounded error.

"""Deterministic BTC checkpoint price forecaster.

Input files end in .in and live in the directory from MAKEFUN_INPUT_DIR or
/input/. Each file holds a case id and a list of per-minute closes. Output
files are named after the case id with .out and live in MAKEFUN_OUTPUT_DIR or
/output/.
"""

import json
import math
import os
from pathlib import Path


MIN_PRICE = 0.00001
MAX_PRICE = 9999999.99999
EMPTY_PRICE = 1.0


def forecast(prices):
    """Calculate and constrain the forecast for a sequence of prices.

    Pull the checkpoint close 35 percent toward the mean of the last 360
    closes and 15 percent toward the mean of the last 1440 closes. For shorter
    lists, each mean uses however many closes exist. Round the result to five
    decimals and clamp it into the allowed price range.
    """
    if not prices:
        return EMPTY_PRICE

    last = next((price for price in reversed(prices) if math.isfinite(price)), None)
    if last is None:
        return EMPTY_PRICE

    trailing_6 = [price for price in prices[-360:] if math.isfinite(price)]
    trailing_24 = [price for price in prices[-1440:] if math.isfinite(price)]
    mean_6 = math.fsum(trailing_6) / len(trailing_6) if trailing_6 else last
    mean_24 = math.fsum(trailing_24) / len(trailing_24) if trailing_24 else last
    value = last + 0.35 * (mean_6 - last) + 0.15 * (mean_24 - last)

    # This guard only keeps pathological input from producing an invalid price.
    if not math.isfinite(value):
        # The weighted result is finite for normal BTC inputs. This fallback
        # also keeps extreme but finite JSON numbers within the output range.
        value = MAX_PRICE if value > 0 else MIN_PRICE
    value = round(value, 5)
    return min(MAX_PRICE, max(MIN_PRICE, value))


def read_case(path):
    """Read and validate one input file; raise ValueError if malformed."""
    with path.open("r", encoding="utf-8") as source:
        data = json.load(source)

    case_id = data["case"]
    markets = data["markets"]
    if not isinstance(case_id, str) or not isinstance(markets, list) or not markets:
        raise ValueError("invalid case or markets")

    prices = markets[0]["prices"]
    if not isinstance(prices, list):
        raise ValueError("prices must be a list")

    clean_prices = []
    for price in prices:
        if isinstance(price, bool) or not isinstance(price, (int, float)):
            raise ValueError("price must be numeric")
        number = float(price)
        if not math.isfinite(number):
            raise ValueError("price must be finite")
        clean_prices.append(number)

    return case_id, clean_prices


def main():
    input_dir = Path(os.environ.get("MAKEFUN_INPUT_DIR", "/input/"))
    output_dir = Path(os.environ.get("MAKEFUN_OUTPUT_DIR", "/output/"))
    output_dir.mkdir(parents=True, exist_ok=True)

    try:
        input_files = sorted(path for path in input_dir.iterdir() if path.is_file() and path.name.endswith(".in"))
    except OSError:
        return

    for input_path in input_files:
        try:
            case_id, prices = read_case(input_path)
            result = {"forecasts": [{"case": case_id, "price": forecast(prices)}]}
            output_path = output_dir / (case_id + ".out")
            with output_path.open("w", encoding="utf-8", newline="\n") as target:
                json.dump(result, target, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
                target.write("\n")
        except (OSError, ValueError, TypeError, KeyError, IndexError, OverflowError, json.JSONDecodeError):
            # A bad input must not prevent later cases from being processed.
            continue


if __name__ == "__main__":
    main()
