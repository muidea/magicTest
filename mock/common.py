"""common"""

import random
import uuid as id
import time as dt
from datetime import datetime, timedelta

# Chinese characters for generating names, words, etc.
CHINESE_CHARS = '的一是在不了有和人这中大为上个国我以要他时来用们生到作地于出就分对成会可主发年动同工也能下过子说产种面而方后多定行学法所民得经十三之进着等部度家电力里如水化高自二理起小物现实加量都两体制机当使点从业本去把性好应开它合还因由其些然前外天政四日那社义事平形相全表间样与关各重新线内数正心反你明看原又么利比或但质气第向道命此变条只没结解问意建月公无系军很情者最立代想已通并提直题党程展五果料象员革位入常文总次品式活设及管特件长求老头基资边流路级少图山统接知较将组见计别她手角期根论运农指几九区强放决西被干做必战先回则任取据处队南给色光门即保治北造百规热领七海口东导器压志世金增争济阶油思术极交受联什认六共权收证改清己美再采转更单风切打白教速花带安场身车例真务具万每目至达走积示议声报斗完类八离华名确才科张信马节话米整空元况今集温传土许步群广石记需段研界拉林律叫且究观越织装影算低持音众书布复容儿须际商非验连断深难近矿千周委素技备半办青省列习响约支般史感劳便团往酸历市克何除消构府称太准精值号率族维划选标写存候毛亲快效斯院查江型眼王按格养易置派层片始却专状育厂京识适属圆包火住调满县局照参红细引听该铁价严'

RAW_CONTENT = 'abcdefghijklmnopqrstuvwxyz'


def uuid():
    return id.uuid4().hex


def int(b=10, e=100):
    return random.randint(b, e)


def float(b=12, e=200):
    return random.uniform(b, e)


def time():
    return dt.strftime("%Y-%m-%d %H:%M:%S", dt.localtime())


def word():
    """Generate a random word"""
    ret = ""
    return ret.join(random.sample(RAW_CONTENT, random.randint(3, 12)))


def chinese_word(length=2):
    """Generate a random Chinese word"""
    return ''.join(random.sample(CHINESE_CHARS, length))


def name():
    """Generate a random Chinese name"""
    return chinese_word(2) + chinese_word(1)


def title(val):
    return val.title()


def sentence():
    """Generate a random sentence"""
    val_array = []
    count = random.randint(5, 13)
    index = 0
    while index < count:
        val_array.append(word())
        index = index + 1

    ret = " "
    return ret.join(val_array) + ". "


def chinese_sentence():
    """Generate a random Chinese sentence"""
    val_array = []
    count = random.randint(5, 13)
    index = 0
    while index < count:
        val_array.append(chinese_word(random.randint(2, 4)))
        index = index + 1

    ret = " "
    return ret.join(val_array) + "。"


def title():
    """Generate a random title"""
    val_array = []
    count = random.randint(5, 10)
    index = 0
    while index < count:
        val_array.append(word())
        index = index + 1

    ret = " "
    return ret.join(val_array)


def chinese_title():
    """Generate a random Chinese title"""
    val_array = []
    count = random.randint(5, 10)
    index = 0
    while index < count:
        val_array.append(chinese_word(random.randint(2, 4)))
        index = index + 1

    ret = " "
    return ret.join(val_array)


def paragraph():
    """Generate a random paragraph"""
    val_array = []
    count = random.randint(5, 10)
    index = 0
    while index < count:
        val_array.append(sentence())
        index = index + 1

    ret = ""
    return ret.join(val_array)


def chinese_paragraph():
    """Generate a random Chinese paragraph"""
    val_array = []
    count = random.randint(5, 10)
    index = 0
    while index < count:
        val_array.append(chinese_sentence())
        index = index + 1

    ret = ""
    return ret.join(val_array)


def content():
    """Generate random content"""
    val_array = []
    count = random.randint(3, 60)
    index = 0
    while index < count:
        val_array.append(paragraph())
        index = index + 1

    ret = "\n"
    return ret.join(val_array)


def chinese_content():
    """Generate random Chinese content"""
    val_array = []
    count = random.randint(3, 60)
    index = 0
    while index < count:
        val_array.append(chinese_paragraph())
        index = index + 1

    ret = "\n"
    return ret.join(val_array)


def email():
    """Generate a random email"""
    url_array = []
    index = 0
    while index < 2:
        url_array.append(word())
        index = index + 1
    domain = '.'
    return '%s@%s' % (word(), domain.join(url_array))


def url():
    """Generate a random URL"""
    url_array = []
    index = 0
    while index < 2:
        url_array.append(word())
        index = index + 1
    domain = '.'
    return domain.join(url_array)


def picker_list(data_list, num):
    """Randomly pick elements from a list"""
    ret = []
    data_len = len(data_list)
    if data_len <= num:
        return data_list.copy()

    tmp_list = data_list[:]
    while True:
        if len(ret) >= num:
            break
        offset = random.randint(0, len(tmp_list) - 1)
        ret.append(tmp_list[offset])
        del tmp_list[offset]
    return ret.copy()


def picker_dict(data_dict, num):
    """Randomly pick elements from a dictionary"""
    ret = {}
    data_len = len(data_dict)
    if data_len <= num:
        return data_dict.copy()

    tmp_dict = data_dict.copy()
    while True:
        if len(ret) >= num:
            break
        offset = random.randint(0, len(tmp_dict) - 1)
        for key in tmp_dict.keys():
            if offset == 0:
                ret[key] = tmp_dict[key]
                tmp_dict.pop(key)
                break
            else:
                offset = offset - 1

    return ret


def date(start_date="2020-01-01", end_date="2023-12-31"):
    """Generate a random date between start_date and end_date"""
    start = datetime.strptime(start_date, "%Y-%m-%d")
    end = datetime.strptime(end_date, "%Y-%m-%d")
    delta = end - start
    random_days = random.randint(0, delta.days)
    return (start + timedelta(days=random_days)).strftime("%Y-%m-%d")


def phone_number():
    """Generate a random phone number"""
    return f"{random.randint(100, 999)}-{random.randint(100, 999)}-{random.randint(1000, 9999)}"


def chinese_phone_number():
    """Generate a random Chinese phone number"""
    return f"1{random.randint(30, 99)}{random.randint(1000, 9999)}{random.randint(1000, 9999)}"


def address():
    """Generate a random address"""
    street_number = random.randint(100, 9999)
    street_name = word().capitalize()
    city = word().capitalize()
    state = random.choice(["北京", "上海", "广州", "深圳", "杭州", "成都", "重庆", "武汉", "南京", "西安"])
    zip_code = random.randint(10000, 99999)
    return f"{street_number} {street_name} St, {city}, {state} {zip_code}"


def chinese_address():
    """Generate a random Chinese address"""
    province = random.choice(["北京", "上海", "广东", "浙江", "四川", "重庆", "湖北", "江苏", "陕西"])
    city = random.choice(["北京市", "上海市", "广州市", "深圳市", "杭州市", "成都市", "重庆市", "武汉市", "南京市", "西安市"])
    district = random.choice(["朝阳区", "浦东新区", "天河区", "南山区", "西湖区", "武侯区", "渝中区", "江汉区", "玄武区", "雁塔区"])
    street = random.choice(["长安街", "南京路", "珠江新城", "科技园路", "西湖大道", "天府大道", "解放碑", "江汉路", "中山路", "雁塔路"])
    number = random.randint(1, 999)
    return f"{province}{city}{district}{street}{number}号"


def boolean():
    """Generate a random boolean value"""
    return random.choice([True, False])


def color():
    """Generate a random color in hex format"""
    return f"#{random.randint(0, 255):02x}{random.randint(0, 255):02x}{random.randint(0, 255):02x}"


def ip_address():
    """Generate a random IP address"""
    return f"{random.randint(0, 255)}.{random.randint(0, 255)}.{random.randint(0, 255)}.{random.randint(0, 255)}"


if __name__ == '__main__':
    print(uuid())
    print(int())
    print(float())
    print(word())
    print(name())
    print(sentence())
    print(title())
    print(paragraph())
    print(content())
    print(email())
    print(date())
    print(phone_number())
    print(address())
    print(boolean())
    print(color())
    print(ip_address())
    print(chinese_word())
    print(chinese_name())
    print(chinese_sentence())
    print(chinese_title())
    print(chinese_paragraph())
    print(chinese_content())
    print(chinese_phone_number())
    print(chinese_address())