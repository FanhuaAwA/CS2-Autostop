from app.autostop.autostop import AutoStop

def print_welcome_info():
    info = """
===========================================================
    CS2 AutoStop - 自动急停工具
    作者: Fanhua
    B站主页: https://space.bilibili.com/3493079266888571
    Github仓库: https://github.com/FanhuaAwA/CS2-Autostop
    提示: 有问题随时可以私信我
    
    声明: 
    该软件为免费开源项目，不支持任何形式的付费或二改付费！
    单纯为技术分享，不涉及任何商业用途。
    如果你是付费购买的，请立即退款并举报卖家。
===========================================================
    """
    print(info)

if __name__ == '__main__':
    print_welcome_info()
    autoStop = AutoStop()