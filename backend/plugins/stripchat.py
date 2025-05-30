import re
import random
from streamlink.plugin import Plugin
from streamlink.plugin.api import validate
from streamlink.stream import HLSStream

_url_re = re.compile(r"https?://(\w+\.)?stripchat\.com/(?P<username>[a-zA-Z0-9_-]+)")


class Stripchat(Plugin):
    @classmethod
    def can_handle_url(cls, url):
        return _url_re.match(url)

    def _get_streams(self):
        data = self.session.http.json(
            self.session.http.get(
                "https://stripchat.com/api/front/v2/models/username/{0}/cam".format(
                    _url_re.match(self.url).group("username")
                ),
                headers={
                    "Content-Type": "application/x-www-form-urlencoded",
                    "X-Requested-With": "XMLHttpRequest",
                    "Referer": self.url,
                },
            )
        )
        num = random.choice(
            [
                "01",
                "02",
                "03",
                "04",
                "05",
                "06",
                "07",
                "08",
                "09",
                "10",
                "11",
                "12",
                "13",
                "14",
                "15",
                "16",
                "17",
                "18",
                "19",
                "20",
                "21",
                "22",
                "23",
                "24",
            ]
        )

        self.logger.info("Stream live: {0}".format(data["user"]["user"]["isLive"]))
        self.logger.info("Stream status: {0}".format(data["user"]["user"]["status"]))

        if data["user"]["user"]["isLive"] is True:
            try:
                for s in HLSStream.parse_variant_playlist(
                    self.session,
                    "https://media-hls.doppiocdn.net/b-hls-{0}/{1}/master_{1}.m3u8".format(
                        num, data["cam"]["streamName"]
                    ),
                    headers={"Referer": self.url},
                    cookies={"stripchat_com_sessionId": "...", "other cookie": "..."},
                ).items():
                    yield s
            except IOError as err:
                stream = HLSStream(
                    self.session,
                    "https://media-hls.doppiocdn.net/b-hls-{0}/{1}/{1}.m3u8".format(
                        num, data["cam"]["streamName"]
                    ),
                    cookies={"stripchat_com_sessionId": "...", "other cookie": "..."},
                )
                yield "Auto", stream


__plugin__ = Stripchat