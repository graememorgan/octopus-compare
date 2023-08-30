import requests
import sys
import datetime
import json
import csv
from rangedict import RangeDict
from dateutil import parser
from tabulate import tabulate

api_key = sys.argv[1]
mpan = sys.argv[2]
serial_number = sys.argv[3]
from_time = sys.argv[4]
to_time = sys.argv[5]


def get_tariffs(from_time, to_time, product_code, tariff_code):
    results = []
    r = requests.get(
        f"https://api.octopus.energy/v1/products/{product_code}/electricity-tariffs/{tariff_code}/standard-unit-rates/",
        params={
            "size": 48,
            "period_from": from_time,
            "period_to": to_time,
            "page_size": 150000,
            "page": 1,
        },
    ).json()
    results.extend(r["results"])
    while r["next"] is not None:
        r = requests.get(r["next"]).json()
        results.extend(r["results"])
    return results


def get_usage(from_time, to_time, api_key, mpan, serial_number):
    return requests.get(
        f"https://api.octopus.energy/v1/electricity-meter-points/{mpan}/meters/{serial_number}/consumption/",
        auth=(api_key, ""),
        params={
            "page_size": 150000,
            "period_from": from_time,
            "period_to": to_time,
            "page": 1,
        },
    ).json()["results"]


def integrate_daily_costs(tariff_map, usages):
    costs = {}
    consumptions = {}
    for usage in usages:
        start = parser.parse(usage["interval_start"])
        date = start.date()
        if date not in costs:
            costs[date] = 0.0
            consumptions[date] = 0.0
        if start.timestamp() not in tariff_map:
            print("Failed to find a tariff at " + str(start), file=sys.stderr)
            continue
        consumption = float(usage["consumption"])
        # Hackity hack: assume that the tariff at the start of the meter reading interval is the currect one.
        # This is fine assuming meter readings are half-hour-aligned and tariffs don't change faster than that.
        costs[date] += tariff_map[start.timestamp()] * consumption
        consumptions[date] += consumption
    return costs, consumptions


def parse_tariffs(tariffs):
    rd = RangeDict()
    for tariff in tariffs:
        start = parser.parse(tariff["valid_from"])
        end = parser.parse(tariff["valid_to"])
        t = float(tariff["value_inc_vat"])
        rd[(start.timestamp(), end.timestamp() - 1)] = t
    return rd


usage = get_usage(from_time, to_time, api_key, mpan, serial_number)

writer = csv.writer(sys.stdout)
output = []

output.append(["Date", "Consumption/kWh"])

for i in range(6, len(sys.argv), 2):
    product_code = sys.argv[i]
    tariff_code = sys.argv[i + 1]

    name = product_code + " " + tariff_code
    output[0].extend([name + " cost/p"])

    tariff = get_tariffs(from_time, to_time, product_code, tariff_code)

    tariff_map = parse_tariffs(tariff)
    costs, consumptions = integrate_daily_costs(tariff_map, usage)
    i = 1
    for date, cost in costs.items():
        if len(output) <= i:
            output.append([str(date), round(consumptions[date], 2)])
        output[i].extend([round(cost, 2)])
        i += 1

for line in output:
    writer.writerow(line)
