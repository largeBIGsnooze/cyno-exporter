import requests
import os
import io
import csv
from bs4 import BeautifulSoup
import re
from datetime import datetime


class FuzzWork:
    def __init__(self):
        self.url = "https://www.fuzzwork.co.uk/dump"
        self.data = {"eveGraphics": {}}

    def _request(self, url):
        response = requests.get(url)
        try:
            if response.status_code == 200:
                return response
        except:
            return None

    def _parse_csv(self, content, file_type):
        if isinstance(content, bytes):
            content = content.decode("utf-8")
        spreadsheet_reader = csv.reader(io.StringIO(content))
        for row in spreadsheet_reader:
            (
                graphicId,
                sofFactionName,
                graphicFile,
                sofHullName,
                sofRaceName,
                description,
            ) = row
            self.data[file_type][sofHullName + ".gr2"] = description + ".gr2"
        return self.data

    def get_latest(self, csv):
        response = self._request(self.url)
        try:
            soup = BeautifulSoup(response.text, "lxml")
            pre = soup.find("pre")
            lines = pre.text.split("\n")
            archive_data = []
            for line in lines[3:]:
                line = line.strip()
                if not line:
                    continue

                line_contents = re.search(
                    "^(\w+\-(\d+)\-\w+\/)\s*(\d{4}\-\d{2}\-\d{2}\s\d{2}\:\d{2})\s*(.*)$",
                    line,
                )
                if line_contents:
                    date = re.search("(\d{4})(\d{2})(\d{2})", line_contents.group(2))
                    if date:
                        archive = line_contents.group(1)
                        year, month, day = date.groups()
                        archive_data.append(
                            {
                                "archive": archive,
                                "dt": datetime(int(year), int(month), int(day)),
                            }
                        )

            minor = max(item["dt"] for item in archive_data)
            latest_archive = next(
                (item for item in archive_data if item["dt"] == minor), None
            )

            if not latest_archive:
                return {}

            csv_file = os.path.join("resindex", f'{latest_archive["archive"][:-1]}.csv')
            os.makedirs(os.path.dirname(csv_file), exist_ok=True)

            if os.path.exists(csv_file):
                with open(csv_file, "r") as r:
                    return self._parse_csv(r.read(), csv[:-4])

            response2 = self._request(self.url + f'/{latest_archive["archive"]}/{csv}')

            with open(csv_file, "wb") as f:
                f.write(response2.content)

            return self._parse_csv(response2.content, csv[:-4])
        except:
            return {}
