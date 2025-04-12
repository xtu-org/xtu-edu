from bs4 import BeautifulSoup, Tag
from urllib import parse
import unicodedata
import httpx
import time

from xtu.edu.captcha import captcha

from const import HEADER, HOST


class XTU:
    def __init__(self, studentId: str, password: str):
        self.studentId = studentId
        self.password = password
        self.client = httpx.AsyncClient(headers=HEADER, timeout=None, http2=True)

    async def login(self):
        """登录"""

        async def _get_encode() -> str:
            """登录请求前 获取加密后的encode"""
            url = parse.urljoin(HOST, "/jsxsd/xk/LoginToXk?flag=sess")
            resp = await self.client.post(url=url)
            resp.raise_for_status()

            res: dict = resp.json()
            data: str = res["data"]

            scode = data.split("#")[0]
            sxh = data.split("#")[1]
            code = f"{self.studentId}%%%{self.password}"
            i = 0
            encode = ""

            while i < len(code):
                if i < 20:
                    encode = encode + code[i : i + 1] + scode[0 : int(sxh[i : i + 1])]
                    scode = scode[int(sxh[i : i + 1]) : len(scode)]
                else:
                    encode = encode + code[i : len(code)]
                    i = len(code)
                i += 1
            return encode

        async def _get_code() -> str:
            """获取图形验证码结果"""
            url = parse.urljoin(HOST, "/jsxsd/verifycode.servlet")
            resp = await self.client.get(url=url)
            code = captcha(resp.content)
            return code

        # 预请求
        url = parse.urljoin(HOST, "/jsxsd/framework/xsMain.jsp")
        resp = await self.client.get(url=url)

        # 登录
        url = parse.urljoin(HOST, "/jsxsd/xk/LoginToXk")
        resp = await self.client.post(
            url=url,
            data={  # 登录
                "USERNAME": self.studentId,
                "PASSWORD": self.password,
                "encoded": await _get_encode(),
                "RANDOMCODE": await _get_code(),
            },
        )
        if resp.status_code != 302:
            if "验证码错误" in resp.text:
                raise Exception("验证码错误")
            elif "用户名或密码错误" in resp.text:
                raise Exception("用户名或密码错误")
            else:
                raise Exception("未知错误")
        # 检查登录结果
        status = await self.check_login()
        if not status:
            raise Exception("登录过期, 请重新登录")
        return self.client.cookies

    async def check_login(self) -> bool:
        """检查是否登录"""
        url = parse.urljoin(HOST, "/jsxsd/framework/xsMain.jsp")
        resp = await self.client.get(url)
        if "请先登录系统" in resp.text:  # 未登录
            return False
        elif not self.studentId or self.studentId in resp.text:  # 不检查学号 or 学号正确
            return True
        else:  # 学号不一致
            return False

    async def get_userinfo(self) -> dict:
        """获取用户信息"""
        url = parse.urljoin(HOST, "/jsxsd/grxx/xsxx")
        resp = await self.client.get(
            url=url,
            params={
                "Ves632DSdyV": "NEW_XSD_XJCJ",
            },
        )
        soup = BeautifulSoup(resp.text, "html.parser")
        table = soup.find("table", id="xjkpTable")
        trs: list[Tag] = table.find_all("tr")
        res: dict = {}
        for tr_index in list(range(3, 11)) + list(range(46, 49)):
            tr: list[Tag] = trs[tr_index].find_all("td")
            for td_index in range(len(tr)):
                if td_index % 2:
                    value = unicodedata.normalize("NFKD", tr[td_index].text).strip()
                    if value:
                        res[tr[td_index - 1].text] = value

        tr: list[Tag] = trs[2].find_all("td")
        for td in tr:
            td_data = td.text.split("：")
            if td_data[1]:
                res[td_data[0]] = td_data[1]
        return res

    async def download_userinfo_file(self) -> bytes:
        """下载用户学籍卡 Excel"""
        url = parse.urljoin(HOST, "/jsxsd/grxx/xsxx_print.do")
        resp = await self.client.get(url=url)
        file = resp.content
        return file

    async def download_user_photo(self) -> bytes:
        """下载用户学籍头像"""
        url = parse.urljoin(HOST, "/jsxsd/grxx/xszpLoad")
        resp = await self.client.get(url=url)
        file = resp.content
        return file

    async def download_score_file(self) -> bytes:
        """下载成绩报表 PDF"""
        url = parse.urljoin(HOST, "/jsxsd/kscj/cjdy_dc")
        resp = await self.client.post(
            url=url,
            params={
                "date": int(time.time() * 1000),
            },
            data={
                "xs0101id": "",
                "cjtype": "",
                "sjlj": "110",
                "sjlj": "120",  # noqa: F601
                "sjcj": "2",
                "bblx": "jg",
            },
        )
        file = resp.content
        return file

    async def get_score(self) -> list[dict]:
        """获取成绩"""
        url = parse.urljoin(HOST, "/jsxsd/kscj/cjcx_list")
        resp = await self.client.post(
            url=url,
            params={
                "xq": "",
            },
            data={
                "kksj": "",
                "kclb": "",
                "kcmc": "",
                "xsfs": "all",
            },
        )
        soup = BeautifulSoup(resp.text, "html.parser")
        table = soup.find("table", id="dataList")
        trs: list[Tag] = table.find_all("tr")
        table_head: list[Tag] = trs[0].find_all("th")
        items = []
        if len(trs) <= 1:
            return []
        for tr in trs[1:]:
            tds: list[Tag] = tr.find_all("td")
            item = {}
            for index, head in enumerate(table_head):
                item[head.text] = tds[index].text
            items.append(item)
        return items

    async def get_score_rank(
        self,
        semester: str = "2023-2024-2",
        mode: str = "必修",
    ) -> dict:
        """获取成绩排名"""
        url = parse.urljoin(HOST, "/jsxsd/kscj/cjjd_list")
        resp = await self.client.post(
            url=url,
            data={
                "kksj": semester,
                "kclb": {"必修": "1", "选修": "7"}[mode],
                "zsb": "0",
            },
        )
        soup = BeautifulSoup(resp.text, "html.parser")
        table = soup.find("table", id="dataList")
        trs: list[Tag] = table.find_all("tr")
        table_head: list[Tag] = trs[0].find_all("th")
        tds: list[Tag] = trs[1].find_all("td")
        item = {}
        for index, head in enumerate(table_head):
            item[head.text] = tds[index].text
        return item

    async def get_all_semester(self) -> list[str]:
        """获取所有学期"""
        url = parse.urljoin(HOST, "/jsxsd/kscj/cjjd_cx")
        resp = await self.client.get(url=url)
        soup = BeautifulSoup(resp.text, "html.parser")
        select = soup.find("select", id="kksj")
        options: list[Tag] = select.find_all("option")
        return [item for item in [option.attrs.get("value") for option in options] if item][:12]

    async def get_training(self) -> list[dict]:
        """获取培养方案"""
        url = parse.urljoin(HOST, "/jsxsd/pyfa/pyfazd_query")
        resp = await self.client.get(url=url)
        soup = BeautifulSoup(resp.text, "html.parser")
        table = soup.find("table", id="dataList")
        trs: list[Tag] = table.find_all("tr")
        table_head: list[Tag] = trs[0].find_all("th")
        items = []
        for tr in trs[1:]:
            tds: list[Tag] = tr.find_all("td")
            item = {}
            for index, head in enumerate(table_head):
                item[head.text] = tds[index].text
            items.append(item)
        return items

    async def get_exam_time(
        self,
        semester: str = "2023-2024-2",
    ) -> list[dict]:
        """获取考试时间"""
        url = parse.urljoin(HOST, "/jsxsd/xsks/xsksap_list")
        resp = await self.client.get(
            url=url,
            params={
                "xnxqid": semester,
            },
        )
        soup = BeautifulSoup(resp.text, "html.parser")
        table = soup.find("table", id="dataList")
        trs: list[Tag] = table.find_all("tr")
        table_head: list[Tag] = trs[0].find_all("th")
        items = []
        for tr in trs[1:]:
            tds: list[Tag] = tr.find_all("td")
            item = {}
            for index, head in enumerate(table_head):
                item[head.text] = tds[index].text
            items.append(item)
        return items

    async def get_rank_exam(self) -> list[dict]:
        """获取竞赛"""
        url = parse.urljoin(HOST, "/jsxsd/syjxxs/toFindXkjsKblb.do")
        resp = await self.client.get(url=url)
        soup = BeautifulSoup(resp.text, "html.parser")
        table = soup.find("table", id="dataList")
        trs: list[Tag] = table.find_all("tr")
        table_head: list[Tag] = trs[0].find_all("th")
        items = []
        for tr in trs[1:]:
            tds: list[Tag] = tr.find_all("td")
            item = {}
            for index, head in enumerate(table_head):
                item[head.text] = tds[index].text
            items.append(item)
        return items

    async def get_empty_room(
        self,
        building: str = "301",
    ) -> list[dict]:
        """获取空教室"""
        url = parse.urljoin(HOST, "/jsxsd/kbxx/kxjs_query")
        resp = await self.client.post(
            url=url,
            data={
                "xqbh": "01",
                "jxlbh": "101",  # 教学楼
                "xzlx": "0",
            },
        )
        soup = BeautifulSoup(resp.text, "html.parser")
        table = soup.find("table", id="dataList")
        trs: list[Tag] = table.find_all("tr")
        table_head: list[Tag] = trs[1].find_all("td")[:11]
        items = []
        for tr in trs[2:]:
            tds: list[Tag] = tr.find_all("td")[:11]
            item = {}
            for index, head in enumerate(table_head):
                item[unicodedata.normalize("NFKD", head.text).strip()] = unicodedata.normalize(
                    "NFKD", tds[index].text
                ).strip()
            items.append(item)
        return items

    async def get_curriculum(
        self,
        semester: str = "2024-2025-1",  # 学期
        week: int = 2,  # 周次
        mode: str = "me",  # me:自己课表 / school:全校课表
        class_: str = "756C5248C5E941DBBE3E714BB24CEA62",  # 班级
    ) -> dict:
        """获取课表"""
        if mode == "school":  # 全校
            url = parse.urljoin(HOST, "/jsxsd/kbcx/kbxx_xzb_ifr")
            resp = await self.client.post(
                url,
                data={
                    "xnxqh": semester,
                    "bj": class_,
                    "zc1": week,
                    "zc2": week,
                },
            )
        else:  # 自己课表
            url = parse.urljoin(HOST, "/jsxsd/xskb/xskb_list.do")
            resp = await self.client.post(
                url,
                data={
                    "zc": week,
                    "xnxq01id": semester,
                },
            )
        soup = BeautifulSoup(resp.text, "html.parser")
        table = soup.find("table", id="kbtable")

        trs: list[Tag] = table.find_all("tr")
        days = {}

        table_head: list[Tag] = trs[0].find_all("th")
        for head in table_head[1:]:
            days[head.text] = {}

        # 只有上帝才知道这一段写的是什么
        for tr in trs[1:]:
            tr_head = unicodedata.normalize("NFKD", tr.find("th").text).strip()
            tr_head = tr_head.replace("，", ",").replace(",10,", "-").replace(",", "-")
            tds: list[Tag] = tr.find_all("td")
            for index, td in enumerate(tds):
                div: Tag = td.find("div", class_="kbcontent")
                days[table_head[index + 1].text][tr_head] = {}
                if div and len(div.contents):
                    if not (name := unicodedata.normalize("NFKD", div.contents[0]).strip()):
                        continue
                    days[table_head[index + 1].text][tr_head] |= {
                        "name": name,
                    }
                    fonts: list[Tag] = div.find_all("font")
                    if fonts and len(fonts):
                        for font in fonts:
                            days[table_head[index + 1].text][tr_head] |= {
                                font.attrs.get("title"): unicodedata.normalize("NFKD", font.text).strip()
                            }
        return days
