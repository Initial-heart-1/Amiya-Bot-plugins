import os
import html
import time
import asyncio

from typing import Awaitable
from amiyabot import TencentBotInstance

from core.database.group import GroupSetting
from core.database.messages import *
from core.util import TimeRecorder, AttrDict
from core import send_to_console_channel, Message, Chain, SourceServer, AmiyaBotPluginInstance, bot as main_bot

from .helper import WeiboUser

curr_dir = os.path.dirname(__file__)


class WeiboPluginInstance(AmiyaBotPluginInstance):
    ...


bot = WeiboPluginInstance(
    name='微博推送',
    version='2.3',
    plugin_id='amiyabot-weibo',
    plugin_type='official',
    description='可在微博更新时自动推送到群',
    document=f'{curr_dir}/README.md',
    instruction=f'{curr_dir}/README_USE.md',
    global_config_schema=f'{curr_dir}/config_schema.json',
    global_config_default=f'{curr_dir}/config_default.yaml'
)


@table
class WeiboRecord(MessageBaseModel):
    user_id: int = IntegerField()
    blog_id: str = CharField()
    record_time: int = IntegerField()


class SendTasks:
    def __init__(self):
        self.tasks = []
        self.done = 0

    def append_task(self, task: Awaitable):
        self.tasks.append(
            self.run_task(task)
        )

    async def run_task(self, task: Awaitable):
        await task
        self.done += 1

    async def run(self, timeout: int):
        for item in self.tasks:
            asyncio.create_task(item)

        time_rec = TimeRecorder()
        while self.done != len(self.tasks):
            await asyncio.sleep(1)

            if time_rec.rec() >= timeout:
                break


async def send_by_index(index: int, weibo: WeiboUser, data: Message):
    result = await weibo.get_weibo_content(index - 1)

    if not result:
        return Chain(data).text('博士…暂时无法获取微博呢…请稍后再试吧')
    else:
        chain = Chain(data) \
            .text(result.user_name + '\n') \
            .text(html.unescape(result.html_text) + '\n') \
            .image(result.pics_list)

        if type(data.instance) is not TencentBotInstance:
            chain.text(f'\n\n{result.detail_url}')

        return chain


@bot.on_message(group_id='weibo', keywords=['开启微博推送'])
async def _(data: Message):
    if not data.is_admin:
        return Chain(data).text('抱歉，微博推送只能由管理员设置')

    channel: GroupSetting = GroupSetting.get_or_none(
        group_id=data.channel_id, bot_id=data.instance.appid
    )
    if channel:
        GroupSetting.update(send_weibo=1).where(
            GroupSetting.group_id == data.channel_id,
            GroupSetting.bot_id == data.instance.appid,
        ).execute()
    else:
        if GroupSetting.get_or_none(group_id=data.channel_id):
            GroupSetting.update(bot_id=data.instance.appid, send_weibo=1).where(
                GroupSetting.group_id == data.channel_id
            ).execute()
        else:
            GroupSetting.create(
                group_id=data.channel_id, bot_id=data.instance.appid, send_weibo=1
            )

    return Chain(data).text('已在本群开启微博推送')


@bot.on_message(group_id='weibo', keywords=['关闭微博推送'])
async def _(data: Message):
    if not data.is_admin:
        return Chain(data).text('抱歉，微博推送只能由管理员设置')

    GroupSetting.update(send_weibo=0).where(GroupSetting.group_id == data.channel_id,
                                            GroupSetting.bot_id == data.instance.appid).execute()

    return Chain(data).text('已在本群关闭微博推送')


@bot.on_message(group_id='weibo', keywords=['微博'])
async def _(data: Message):
    message = data.text_digits
    index = 0

    r = re.search(r'(\d+)', message)
    if r:
        index = abs(int(r.group(1)))

    if '最新' in message:
        index = 1

    weibo = WeiboUser(bot.get_config('listen')[0], AttrDict(bot.get_config('setting')))

    if index:
        return await send_by_index(index, weibo, data)
    else:
        result = await weibo.get_blog_list()
        user_name = await weibo.get_user_name()
        if not result:
            return Chain(data).text('博士…暂时无法获取微博列表呢…请稍后再试吧')

        reply = Chain(data) \
            .text(f'这是 {user_name} 的微博列表') \
            .text_image(result) \
            .text('回复【序号】或和我说「阿米娅第 N 条微博」来获取详情吧')

        wait = await data.wait(reply)
        if wait:
            r = re.search(r'(\d+)', wait.text_digits)
            if r:
                index = abs(int(r.group(1)))
                return await send_by_index(index, weibo, wait)


@bot.timed_task(each=30)
async def _(_):
    for user in bot.get_config('listen'):
        weibo = WeiboUser(user, AttrDict(bot.get_config('setting')))
        new_id = await weibo.get_weibo_id(0)
        if not new_id:
            continue

        record = WeiboRecord.get_or_none(blog_id=new_id)
        if record:
            continue

        WeiboRecord.create(user_id=user, blog_id=new_id, record_time=int(time.time()))

        target: List[GroupSetting] = GroupSetting.select().where(
            GroupSetting.send_weibo == 1
        )

        if not target:
            continue

        time_rec = TimeRecorder()
        send_tasks = SendTasks()

        result = await weibo.get_weibo_content(0)
        images_urls = []

        if not result:
            await send_to_console_channel(Chain().text(f'微博获取失败\nUSER: {user}\nID: {new_id}'))
            return

        await send_to_console_channel(
            Chain().text(f'开始推送微博\nUSER: {result.user_name}\nID: {new_id}\n目标数: {len(target)}')
        )

        for item in target:
            data = Chain()

            instance = main_bot[item.bot_id]

            if not instance:
                continue

            data.text(f'来自 {result.user_name} 的最新微博\n\n{html.unescape(result.html_text)}')

            if type(instance.instance) is TencentBotInstance:
                if not instance.private:
                    if not images_urls and result.pics_list:
                        for pic in result.pics_list:
                            with open(pic, mode='rb') as p:
                                images_urls.append(
                                    await SourceServer.image_getter_hook(p.read())
                                )
                    data.image(images_urls)
                else:
                    data.image(result.pics_list)
            else:
                data.image(result.pics_list).text(f'\n\n{result.detail_url}')

            if bot.get_config('sendAsync'):
                send_tasks.append_task(
                    instance.send_message(data, channel_id=item.group_id)
                )
            else:
                await instance.send_message(data, channel_id=item.group_id)
                await asyncio.sleep(bot.get_config('sendInterval'))

        if send_tasks.tasks:
            await send_tasks.run(20 * 60)

        await send_to_console_channel(Chain().text(f'微博推送结束:\n{new_id}\n耗时{time_rec.total()}'))
