import webbrowser
from sys import exit

import win32api

from config import load_config, config, XinYueOperationConfig
from djc_helper import DjcHelper
from log import asciiReset
from qzone_activity import QzoneActivity
from setting import *
from update import check_update_on_start
from util import *
from version import *


def has_any_account_in_normal_run(cfg):
    for _idx, account_config in enumerate(cfg.account_configs):
        if not account_config.is_enabled():
            # 未启用的账户的账户不走该流程
            continue

        return True
    return False


def _show_head_line(msg):
    show_head_line(msg, color("fg_bold_yellow"))


def check_djc_role_binding():
    load_config("config.toml", "config.toml.local")
    cfg = config()

    if not has_any_account_in_normal_run(cfg):
        logger.warning("未发现任何有效的账户配置，请检查配置文件")
        os.system("PAUSE")
        exit(-1)

    _show_head_line("启动时检查各账号是否在道聚城绑定了dnf账号和任意手游账号")

    while True:
        all_binded = True

        for _idx, account_config in enumerate(cfg.account_configs):
            idx = _idx + 1
            if not account_config.is_enabled():
                # 未启用的账户的账户不走该流程
                continue

            logger.warning(color("fg_bold_yellow") + "------------检查第{}个账户({})------------".format(idx, account_config.name))
            djcHelper = DjcHelper(account_config, cfg.common)
            if not djcHelper.check_djc_role_binding():
                all_binded = False

        if all_binded:
            break
        else:
            logger.warning(color("fg_bold_yellow") + "请前往道聚城将上述提示的未绑定dnf或任意手游的账号进行绑定，具体操作流程可以参考使用文档或者教学视频。")
            logger.warning(color("fg_bold_yellow") + "如果本账号不需要道聚城相关操作，可以打开配置表，将该账号的cannot_bind_dnf设为true，game_name设为无，即可跳过道聚城相关操作")
            logger.warning(color("fg_bold_yellow") + "  ps: 上面这个cannot_bind_dnf之前笔误写成了cannot_band_dnf，如果之前填过，请手动把配置名称改成cannot_bind_dnf~")
            logger.warning(color("fg_bold_cyan") + "操作完成后点击任意键即可再次进行检查流程...")
            os.system("PAUSE")

            # 这时候重新读取一遍用户修改过后的配置文件（比如把手游设为了 无 ）
            load_config("config.toml", "config.toml.local")
            cfg = config()


def check_all_skey_and_pskey(cfg):
    if not has_any_account_in_normal_run(cfg):
        return
    _show_head_line("启动时检查各账号skey/pskey/openid是否过期")

    for _idx, account_config in enumerate(cfg.account_configs):
        idx = _idx + 1
        if not account_config.is_enabled():
            # 未启用的账户的账户不走该流程
            continue

        logger.warning(color("fg_bold_yellow") + "------------检查第{}个账户({})------------".format(idx, account_config.name))
        djcHelper = DjcHelper(account_config, cfg.common)
        djcHelper.check_skey_expired()
        djcHelper.get_bind_role_list(print_warning=False)
        djcHelper.fetch_pskey()
        # djcHelper.fetch_guanjia_openid(print_warning=False)


def auto_send_cards(cfg):
    if not has_any_account_in_normal_run(cfg):
        return
    _show_head_line("运行完毕自动赠送卡片")

    target_qqs = cfg.common.auto_send_card_target_qqs
    if len(target_qqs) == 0:
        logger.warning("未定义自动赠送卡片的对象QQ数组，将跳过本阶段")
        return

    # 统计各账号卡片数目
    logger.info("拉取各账号的卡片数据中，请耐心等待...")
    qq_to_card_name_to_counts = {}
    qq_to_prize_counts = {}
    qq_to_djcHelper = {}
    for _idx, account_config in enumerate(cfg.account_configs):
        idx = _idx + 1
        if not account_config.is_enabled():
            # 未启用的账户的账户不走该流程
            continue

        djcHelper = DjcHelper(account_config, cfg.common)
        djcHelper.check_skey_expired()
        djcHelper.get_bind_role_list(print_warning=False)

        lr = djcHelper.fetch_pskey()
        if lr is None:
            continue

        qq = uin2qq(lr.uin)
        qa = QzoneActivity(djcHelper, lr)

        qq_to_card_name_to_counts[qq] = qa.get_card_counts()
        qq_to_prize_counts[qq] = qa.get_prize_counts()
        qq_to_djcHelper[qq] = djcHelper

        logger.info("{}/{} 账号 {:} 的数据拉取完毕".format(idx, len(cfg.account_configs), padLeftRight(account_config.name, 12)))

    # 赠送卡片
    for idx, target_qq in enumerate(target_qqs):
        if target_qq in qq_to_djcHelper:
            left_times = qq_to_djcHelper[target_qq].ark_lottery_query_left_times(target_qq)
            logger.warning(color("fg_bold_green") + "第{}/{}个赠送目标账号 {}({}) 今日仍可被赠送 {} 次卡片".format(
                idx + 1, len(target_qqs), qq_to_djcHelper[target_qq].cfg.name, target_qq, left_times
            ))
            # 最多赠送目标账号今日仍可接收的卡片数
            for i in range(left_times):
                send_card(target_qq, qq_to_card_name_to_counts, qq_to_prize_counts, qq_to_djcHelper, target_qqs)

            # 赠送卡片完毕后尝试抽奖
            djcHelper = qq_to_djcHelper[target_qq]
            lr = djcHelper.fetch_pskey()
            if lr is not None:
                qa = QzoneActivity(djcHelper, lr)
                qa.try_lottery_using_cards(print_warning=False)


def send_card(target_qq, qq_to_card_name_to_counts, qq_to_prize_counts, qq_to_djcHelper, target_qqs):
    card_info_map = parse_card_group_info_map(qq_to_djcHelper[target_qq].zzconfig)
    # 检查目标账号是否有可剩余的兑换奖励次数
    has_any_left_gift = False
    for name, count in qq_to_prize_counts[target_qq].items():
        if count > 0:
            has_any_left_gift = True

    target_card_infos = []
    if has_any_left_gift:
        logger.debug("仍有可兑换奖励，将赠送目标QQ最需要的卡片")
        # 当前账号的卡牌按照卡牌数升序排列
        for card_name, card_count in qq_to_card_name_to_counts[target_qq].items():
            target_card_infos.append((card_name, card_count))
        target_card_infos.sort(key=lambda card: card[1])
    else:
        logger.debug("所有奖励都已兑换，将赠送目标QQ其他QQ最富余的卡片")
        # 统计其余账号的各卡牌总数
        merged_card_name_to_count = {}
        for qq, card_name_to_count in qq_to_card_name_to_counts.items():
            for card_name, card_count in card_name_to_count.items():
                merged_card_name_to_count[card_name] = merged_card_name_to_count.get(card_name, 0) + card_count
        # 降序排列
        for card_name, card_count in merged_card_name_to_count.items():
            target_card_infos.append((card_name, card_count))
        target_card_infos.sort(key=lambda card: -card[1])

    # 升序遍历
    for card_name, card_count in target_card_infos:
        # 找到任意一个拥有卡片的其他账号，让他送给目标账户。默认越靠前的号越重要，因此从后面的号开始查
        for qq, card_name_to_count in reverse_map(qq_to_card_name_to_counts):
            if qq in target_qqs:
                continue
            # 如果某账户有这个卡，则赠送该当前玩家，并结束本回合赠卡
            if card_name_to_count[card_name] > 0:
                qq_to_djcHelper[qq].send_card(card_info_map[card_name].id, target_qq)
                card_name_to_count[card_name] -= 1
                qq_to_card_name_to_counts[target_qq][card_name] += 1

                logger.warning(color("fg_bold_cyan") + "账号 {} 赠送一张 {}({}) 给 {}".format(
                    qq_to_djcHelper[qq].cfg.name,
                    card_info_map[card_name].index, card_name,
                    qq_to_djcHelper[target_qq].cfg.name
                ))
                return


def reverse_map(map):
    kvs = list(map.items())
    kvs.reverse()
    return kvs


def show_lottery_status(ctx, cfg, need_show_tips=False):
    if not has_any_account_in_normal_run(cfg):
        return
    _show_head_line(ctx)

    end_time = "2020-12-31"
    remaining_time = datetime.datetime.strptime(end_time, "%Y-%m-%d") - datetime.datetime.now()
    logger.info(color("bold_black") + "本次集卡活动的结束时间为{}，剩余时间为{}".format(end_time, remaining_time))

    lottery_zzconfig = zzconfig()
    card_info_map = parse_card_group_info_map(lottery_zzconfig)
    order_map = {}
    # 卡片编码 => 名称
    for name, card_info in card_info_map.items():
        order_map[card_info.index] = name

    # 奖励展示名称 => 实际名称
    groups = [
        lottery_zzconfig.prizeGroups.group1,
        lottery_zzconfig.prizeGroups.group2,
        lottery_zzconfig.prizeGroups.group3,
        lottery_zzconfig.prizeGroups.group4,
    ]
    prizeDisplayTitles = []
    for group in groups:
        displayTitle = group.title
        if len(displayTitle) > 4 and "礼包" in displayTitle:
            # 将 全民竞速礼包 这种名称替换为 全民竞速
            displayTitle = displayTitle.replace("礼包", "")

        order_map[displayTitle] = group.title
        prizeDisplayTitles.append(displayTitle)

    heads = []
    colSizes = []

    baseHeads = ["序号", "账号名"]
    baseColSizes = [4, 12]
    heads.extend(baseHeads)
    colSizes.extend(baseColSizes)

    card_indexes = ["1-1", "1-2", "1-3", "1-4", "2-1", "2-2", "2-3", "2-4", "3-1", "3-2", "3-3", "3-4"]
    card_width = 3
    heads.extend(card_indexes)
    colSizes.extend([card_width for i in card_indexes])

    prize_indexes = [*prizeDisplayTitles]
    heads.extend(prize_indexes)
    colSizes.extend([printed_width(name) for name in prize_indexes])

    accounts_that_should_enable_cost_card_to_lottery = []

    logger.info(tableify(heads, colSizes))
    summaryCols = [1, "总计", *[0 for card in card_indexes], *[count_with_color(0, "bold_green", show_width=printed_width(prize_index)) for prize_index in prize_indexes]]
    for _idx, account_config in enumerate(cfg.account_configs):
        idx = _idx + 1
        if not account_config.is_enabled():
            # 未启用的账户的账户不走该流程
            continue

        if not account_config.ark_lottery.show_status:
            continue

        djcHelper = DjcHelper(account_config, cfg.common)
        djcHelper.check_skey_expired()
        djcHelper.get_bind_role_list(print_warning=False)

        lr = djcHelper.fetch_pskey()
        if lr is None:
            continue

        qa = QzoneActivity(djcHelper, lr)

        card_counts = qa.get_card_counts()
        prize_counts = qa.get_prize_counts()

        summaryCols[0] += 1

        cols = [idx, account_config.name]
        has_any_card = False
        has_any_left_gift = False
        # 处理各个卡片数目
        for card_position, card_index in enumerate(card_indexes):
            card_count = card_counts[order_map[card_index]]

            cols.append(colored_count(idx, card_count, account_config.ark_lottery.show_color))

            # 更新统计信息
            summaryCols[len(baseHeads) + card_position] += card_count

            if card_count > 0:
                has_any_card = True

        # 处理各个奖励剩余领取次数
        for prize_index in prize_indexes:
            prize_count = prize_counts[order_map[prize_index]]
            cols.append(count_with_color(prize_count, "bold_green", show_width=printed_width(prize_index)))

            if prize_count > 0:
                has_any_left_gift = True

        logger.info(tableify(cols, colSizes))

        if has_any_card and not has_any_left_gift:
            accounts_that_should_enable_cost_card_to_lottery.append(account_config.name)

    for cardIdx in range(len(card_indexes)):
        idx = len(baseHeads) + cardIdx
        summaryCols[idx] = colored_count(len(cfg.account_configs), summaryCols[idx], cfg.common.ark_lottery_summary_show_color or "fg_thin_cyan")

    logger.info(tableify(summaryCols, colSizes))

    if need_show_tips and len(accounts_that_should_enable_cost_card_to_lottery) > 0:
        msg = "账户({})仍有剩余卡片，但已无任何可领取礼包，建议开启消耗卡片来抽奖的功能".format(', '.join(accounts_that_should_enable_cost_card_to_lottery))
        logger.warning(color("fg_bold_yellow") + msg)


def colored_count(accountIdx, card_count, show_color=""):
    # 特殊处理色彩
    if card_count == 0:
        if accountIdx == 1:
            # 突出显示大号没有的卡片
            show_count = count_with_color(card_count, "fg_bold_cyan")
        else:
            # 小号没有的卡片直接不显示，避免信息干扰
            show_count = ""
    else:
        if accountIdx == 1:
            if card_count == 1:
                # 大号只有一张的卡片也特殊处理
                show_count = count_with_color(card_count, "fg_bold_blue")
            else:
                # 大号其余卡片亮绿色
                show_count = count_with_color(card_count, "fg_bold_green")
        else:
            # 小号拥有的卡片淡化处理，方便辨识
            show_color = show_color or "fg_bold_black"
            show_count = count_with_color(card_count, show_color)

    return show_count


def count_with_color(card_count, show_color, show_width=3):
    return color(show_color) + padLeftRight(card_count, show_width) + asciiReset + color("INFO")


def show_accounts_status(cfg, ctx):
    if not has_any_account_in_normal_run(cfg):
        return
    _show_head_line(ctx)

    heads = ["序号", "账号名", "启用状态", "聚豆余额", "聚豆历史总数", "成就点", "心悦组队"]
    colSizes = [4, 12, 8, 8, 12, 6, 8]

    logger.info(tableify(heads, colSizes))
    for _idx, account_config in enumerate(cfg.account_configs):
        idx = _idx + 1
        if not account_config.is_enabled():
            # 未启用的账户的账户不走该流程
            continue

        djcHelper = DjcHelper(account_config, cfg.common)
        djcHelper.check_skey_expired()

        status = "启用" if account_config.is_enabled() else "未启用"

        djc_info = djcHelper.query_balance("查询聚豆概览", print_res=False)["data"]
        djc_allin, djc_balance = int(djc_info['allin']), int(djc_info['balance'])

        xinyue_info = djcHelper.query_xinyue_info("查询心悦成就点概览", print_res=False)
        teaminfo = djcHelper.query_xinyue_teaminfo(print_res=False)
        team_score = "无队伍"
        if teaminfo.id != "":
            team_score = "{}/20".format(teaminfo.score)
            fixed_team = djcHelper.get_fixed_team()
            if fixed_team is not None:
                team_score = "[{}]{}".format(fixed_team.id, team_score)

        cols = [idx, account_config.name, status, djc_balance, djc_allin, xinyue_info.score, team_score]

        logger.info(color("fg_bold_green") + tableify(cols, colSizes))


def try_join_xinyue_team(cfg):
    if not has_any_account_in_normal_run(cfg):
        return
    _show_head_line("尝试加入心悦固定队")

    for idx, account_config in enumerate(cfg.account_configs):
        idx += 1
        if not account_config.is_enabled():
            # 未启用的账户的账户不走该流程
            continue

        logger.info("")
        logger.warning(color("fg_bold_yellow") + "------------尝试第{}个账户({})------------".format(idx, account_config.name))

        djcHelper = DjcHelper(account_config, cfg.common)
        djcHelper.check_skey_expired()
        # 尝试加入固定心悦队伍
        djcHelper.try_join_fixed_xinyue_team()

        if cfg.common._debug_run_first_only:
            logger.warning("调试开关打开，不再处理后续账户")
            break


def run(cfg):
    _show_head_line("开始核心逻辑")

    for idx, account_config in enumerate(cfg.account_configs):
        idx += 1
        if not account_config.is_enabled():
            logger.info("第{}个账号({})未启用，将跳过".format(idx, account_config.name))
            continue

        _show_head_line("开始处理第{}个账户({})".format(idx, account_config.name))

        djcHelper = DjcHelper(account_config, cfg.common)
        djcHelper.run()

        if cfg.common._debug_run_first_only:
            logger.warning("调试开关打开，不再处理后续账户")
            break


def try_take_xinyue_team_award(cfg):
    if not has_any_account_in_normal_run(cfg):
        return
    _show_head_line("尝试领取心悦组队奖励")

    # 所有账号运行完毕后，尝试领取一次心悦组队奖励，避免出现前面角色还没完成，后面的完成了，前面的却没领奖励
    for idx, account_config in enumerate(cfg.account_configs):
        idx += 1
        if not account_config.is_enabled():
            # 未启用的账户的账户不走该流程
            continue

        logger.info("")
        logger.warning(color("fg_bold_green") + "------------开始尝试为第{}个账户({})领取心悦组队奖励------------".format(idx, account_config.name))

        if len(account_config.xinyue_operations) == 0:
            logger.warning("未设置心悦相关操作信息，将跳过")
            continue

        djcHelper = DjcHelper(account_config, cfg.common)
        xinyue_info = djcHelper.query_xinyue_info("获取心悦信息", print_res=False)

        op_cfgs = [("513818", "查询小队信息"), ("514385", "领取组队奖励")]

        xinyue_operations = []
        for opcfg in op_cfgs:
            op = XinYueOperationConfig()
            op.iFlowId, op.sFlowName = opcfg
            op.count = 1
            xinyue_operations.append(op)

        for op in xinyue_operations:
            djcHelper.do_xinyue_op(xinyue_info.xytype, op)

        if cfg.common._debug_run_first_only:
            logger.warning("调试开关打开，不再处理后续账户")
            break


def try_xinyue_sailiyam_start_work(cfg):
    if not has_any_account_in_normal_run(cfg):
        return
    _show_head_line("尝试派赛利亚出去打工")

    for idx, account_config in enumerate(cfg.account_configs):
        idx += 1
        if not account_config.is_enabled():
            # 未启用的账户的账户不走该流程
            continue

        logger.info("")
        logger.warning(color("fg_bold_green") + "------------开始处理第{}个账户({})的赛利亚的打工和领工资~------------".format(idx, account_config.name))

        djcHelper = DjcHelper(account_config, cfg.common)
        if account_config.function_switches.get_xinyue_sailiyam:
            # 先尝试领工资
            djcHelper.show_xinyue_sailiyam_work_log()
            djcHelper.xinyue_sailiyam_op("领取工资", "714229", iPackageId=djcHelper.get_xinyue_sailiyam_package_id())
            djcHelper.xinyue_sailiyam_op("全勤奖", "715724")

            # 然后派出去打工
            djcHelper.xinyue_sailiyam_op("出去打工", "714255")

            logger.info("等待一会，避免请求过快")
            time.sleep(3)

        logger.info(color("fg_bold_cyan") + djcHelper.get_xinyue_sailiyam_workinfo())
        logger.info(color("fg_bold_cyan") + djcHelper.get_xinyue_sailiyam_status())


def show_support_pic(cfg):
    logger.info("")
    logger.warning(color("fg_bold_cyan") + "如果觉得我的小工具对你有所帮助，想要支持一下我的话，可以打开支持一下.png，扫码打赏哦~")
    if cfg.common.show_support_pic or is_weekly_first_run():
        os.popen("支持一下.png")


def check_update(cfg):
    logger.info((
        "\n"
        "++++++++++++++++++++++++++++++++++++++++\n"
        "全部账号操作已经成功完成\n"
        "现在准备访问github仓库相关页面来检查是否有新版本\n"
        "由于国内网络问题，访问可能会比较慢，请不要立即关闭，可以选择最小化或切换到其他窗口0-0\n"
        "若有新版本会自动弹窗提示~\n"
        "++++++++++++++++++++++++++++++++++++++++\n"
    ))
    check_update_on_start(cfg.common)


def show_ask_message_box_only_once():
    # 临时加一个请求帮忙弄下红包活动的逻辑
    if is_first_run("a20201110packet"):
        message = (
            "今天看到有个【DPL大狂欢 邀请好友拆红包】，类似于拼多多，需要找其他人在自己的邀请页面中登录并绑定角色，进度足够就可以获得一个红包了\n"
            "大家可不可以帮我点一下哇0-0  点开链接后登录然后绑定角色就OK啦，提前谢谢大家啦0-0 就当是一直免费维护和更新这个小工具的小报酬啦^_^\n"
            "ps: 点确定就会弹出我的邀请页面啦，点否就再也不会弹出这个窗口啦\n"
        )
        res = win32api.MessageBox(0, message, "请求各位帮忙助力一下~", win32con.MB_OKCANCEL)
        if res == win32con.IDOK:
            webbrowser.open("https://dnf.qq.com/cp/a20201110packet/index.html?inviter=2637262711&&gameId=1006")
            win32api.MessageBox(0, "在网页里登录并绑定就完事啦，很快的~多谢啦，嘿嘿嘿0-0", "致谢", win32con.MB_ICONINFORMATION)
        else:
            win32api.MessageBox(0, "嘤嘤嘤", "TAT", win32con.MB_ICONINFORMATION)


def temp_code(cfg):
    if not has_any_account_in_normal_run(cfg):
        return
    _show_head_line("一些小提示")

    tips = [
        (
            "微信的DNF签到和2020DNF嘉年华派送好礼活动目前由于技术问题，无法稳定获取微信登录态，故而无法加入小助手。"
            "若想自动完成，推荐使用auto.js来实现签到功能，使用auto.js自带的定时操作或tasker来实现定时触发签到流程。"
            "具体操作可参考网盘中[DNF蚊子腿小助手 auto.js版本.txt]相关内容。"
            "hello语音等其他蚊子腿也可以通过类似方法完成~"
        ),
        (
            "DNF进击吧赛利亚活动推荐每天运行两次，间隔超过五小时，同时确保第一次运行时已在线30分钟，这样就可以第一次放出去打工，第二次完成打工领取奖励"
        ),
    ]

    for idx, tip in enumerate(tips):
        logger.warning(color("fg_bold_yellow") + "{}. {}\n ".format(idx + 1, tip))


def _test_main():
    need_check_bind_and_skey = True

    # # 最大化窗口
    # logger.info("尝试最大化窗口，打包exe可能会运行的比较慢")
    # maximize_console()

    logger.warning("开始运行DNF蚊子腿小助手，ver={} {}，powered by {}".format(now_version, ver_time, author))
    logger.warning(color("fg_bold_cyan") + "如果觉得我的小工具对你有所帮助，想要支持一下我的话，可以帮忙宣传一下或打开支持一下.png，扫码打赏哦~")

    if need_check_bind_and_skey:
        check_djc_role_binding()

    # 读取配置信息
    load_config("config.toml", "config.toml.local")
    cfg = config()

    if len(cfg.account_configs) == 0:
        logger.error("未找到有效的账号配置，请检查是否正确配置。ps：多账号版本配置与旧版本不匹配，请重新配置")
        exit(-1)

    if need_check_bind_and_skey:
        check_all_skey_and_pskey(cfg)

    # note: 用于本地测试main的相关逻辑
    # show_accounts_status(cfg, "启动时展示账号概览")
    # try_join_xinyue_team(cfg)
    # run(cfg)
    # try_take_xinyue_team_award(cfg)
    # try_xinyue_sailiyam_start_work(cfg)
    show_lottery_status("运行完毕展示各账号抽卡卡片以及各礼包剩余可领取信息", cfg, need_show_tips=True)
    # auto_send_cards(cfg)
    # show_lottery_status("卡片赠送完毕后展示各账号抽卡卡片以及各礼包剩余可领取信息", cfg)
    # show_accounts_status(cfg, "运行完毕展示账号概览")
    # show_support_pic(cfg)
    # temp_code(cfg)
    # if cfg.common._show_usage:
    #     show_usage()
    # check_update(cfg)


if __name__ == '__main__':
    _test_main()
