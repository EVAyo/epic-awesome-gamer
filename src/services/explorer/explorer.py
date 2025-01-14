# -*- coding: utf-8 -*-
# Time       : 2022/1/17 15:20
# Author     : QIN2DIM
# Github     : https://github.com/QIN2DIM
# Description:
import typing
from json.decoder import JSONDecodeError

import cloudscraper
from loguru import logger

from services.utils import ToolBox, get_challenge_ctx
from .core import EpicAwesomeExplorer, GameLibManager
from .exceptions import DiscoveryTimeoutException


class Explorer(EpicAwesomeExplorer):
    """商城探索者 发现常驻免费游戏以及周免游戏"""

    cdn_image_urls = []

    def __init__(self, email: str, silence: typing.Optional[bool] = None):
        super().__init__(silence=silence)
        self.action_name = "Explorer"
        self.game_manager = GameLibManager(email=email)

    def discovery_free_games(
        self,
        ctx_cookies: typing.Optional[typing.List[dict]] = None,
        category: str = "game",
        silence: bool = None,
    ) -> typing.Optional[typing.List[dict]]:
        """
        发现免费游戏。

        本周免费 + 常驻免费
        ________________________________________________________
        1. 此接口可以不传 cookie，免费游戏是公开可见的。
        2. 但如果要查看免费游戏的在库状态，需要传 COOKIE 区分用户。
            - 有些游戏不同地区的玩家不一定都能玩。这个限制和账户地区信息有关，和当前访问的（代理）IP 无关。
            - 请确保传入的 COOKIE 是有效的。
        :param silence:
        :param category: 搜索模式 self.category.keys()
        :param ctx_cookies: ToolBox.transfer_cookies(api.get_cookies())
        :return:
        """
        category = "game" if category not in self.category_details else category
        silence = self.silence if silence is None else silence

        # 创建驱动上下文
        try:
            with get_challenge_ctx(silence=silence) as ctx:
                self._discovery_free_games(ctx=ctx, ctx_cookies=ctx_cookies, category=category)
        except DiscoveryTimeoutException as err:
            logger.error(err)

        # 提取游戏平台对象
        game_objs = list(self.game_objs.values())

        # 运行缓存持久化
        self.game_manager.save_game_objs(game_objs, category=category)

        # 返回实例列表
        return game_objs

    def get_promotions(
        self, ctx_cookies: typing.List[dict]
    ) -> typing.List[typing.Dict[str, typing.Union[str, bool]]]:
        """
        获取周免游戏数据

        <即将推出> promotion["promotions"]["upcomingPromotionalOffers"]
        <本周免费> promotion["promotions"]["promotionalOffers"]
        :param ctx_cookies:
        :return: {"pageLink1": "pageTitle1", "pageLink2": "pageTitle2", ...}
        """
        detailed = []
        headers = {
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/100.0.4896.75 Safari/537.36 Edg/100.0.1185.36",
            "cookie": ToolBox.transfer_cookies(ctx_cookies),
        }
        scraper = cloudscraper.create_scraper()
        response = scraper.get(self.URL_PROMOTIONS, headers=headers)

        try:
            data = response.json()
        except JSONDecodeError:
            pass
        else:
            elements = data["data"]["Catalog"]["searchStore"]["elements"]
            promotions = [e for e in elements if e.get("promotions")]
            # 获取商城促销数据&&获取<本周免费>的游戏对象
            for promotion in promotions:
                if promotion["promotions"]["promotionalOffers"]:
                    image_url = ""
                    try:
                        url = (
                            self.URL_PRODUCT_PAGE
                            + promotion["catalogNs"]["mappings"][0]["pageSlug"]
                        )
                    except IndexError:
                        url = self.URL_PRODUCT_PAGE + promotion["productSlug"]
                    try:
                        image_url = promotion["keyImages"][-1]["url"]
                        Explorer.cdn_image_urls.append(image_url)
                    except (KeyError, IndexError, AttributeError):
                        pass
                    # Implement Promotion Interface
                    detailed.append(
                        {
                            "url": url,
                            "title": promotion["title"],
                            "image_url": image_url,
                            "in_library": None,
                            "namespace": promotion["namespace"],
                        }
                    )

        return detailed

    def get_promotions_by_stress_expressions(
        self, ctx_session=None
    ) -> typing.Dict[str, typing.Union[typing.List[str], str]]:
        """使用应力表达式萃取商品链接"""
        free_game_objs = {}
        if ctx_session:
            critical_memory = ctx_session.current_window_handle
            try:
                ctx_session.switch_to.new_window("tab")
                pending_games: typing.Dict[str, str] = self.stress_expressions(ctx=ctx_session)
            finally:
                ctx_session.switch_to.window(critical_memory)
        else:
            with get_challenge_ctx(silence=self.silence) as ctx:
                pending_games: typing.Dict[str, str] = self.stress_expressions(ctx=ctx)

        if pending_games:
            for url, title in pending_games.items():
                free_game_objs[url] = title
        return free_game_objs
