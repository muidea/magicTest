"""common - Faker-based mock data generator"""

import random
import uuid as id
import time as dt
from datetime import datetime, timedelta
from faker import Faker

# Create Faker instances for different locales
_faker_en = Faker()
_faker_zh = Faker('zh_CN')


def generate_uuid():
    """Generate a random UUID (hex string)"""
    return id.uuid4().hex


def random_int(b=10, e=100):
    """Generate a random integer between b and e (inclusive)"""
    return random.randint(b, e)


def random_float(b=12.0, e=200.0):
    """Generate a random float between b and e"""
    return random.uniform(b, e)


def current_time():
    """Generate current time formatted as YYYY-MM-DD HH:MM:SS"""
    return dt.strftime("%Y-%m-%d %H:%M:%S", dt.localtime())


def word():
    """Generate a random word"""
    return _faker_en.word()


def chinese_word(length=2):
    """Generate a random Chinese word"""
    # Faker doesn't have direct Chinese word generator
    # For short lengths, use a pool of common Chinese characters
    if length <= 0:
        return ''
    
    # Generate longer text and extract characters
    min_chars = max(5, length * 2)  # Ensure at least 5 characters for faker.text()
    text = _faker_zh.text(max_nb_chars=min_chars).replace(' ', '').replace('\n', '')
    
    # If text is too short, pad with common characters
    common_chars = '的一是在不了有和人这中大为上个国我以要他时来用们生到作地于出就分对成会可主发年动同工也能下过子说产种面而方后多定行学法所民得经十三之进着等部度家电力里如水化高自二理起小物现实加量都两体制机当使点从业本去把性好应开它合还因由其些然前外天政四日那社义事平形相全表间样与关各重新线内数正心反你明看原又么利比或但质气第向道命此变条只没结解问意建月公无系军很情者最立代想已通并提直题党程展五果料象员革位入常文总次品式活设及管特件长求老头基资边流路级少图山统接知较将组见计别她手角期根论运农指几九区强放决西被干做必战先回则任取据处队南给色光门即保治北造百规热领七海口东导器压志世金增争济阶油思术极交受联什认六共权收证改清己美再采转更单风切打白教速花带安场身车例真务具万每目至达走积示议声报斗完类八离华名确才科张信马节话米整空元况今集温传土许步群广石记需段研界拉林律叫且究观越织装影算低持音众书布复容儿须际商非验连断深难近矿千周委素技备半办青省列习响约支般史感劳便团往酸历市克何除消构府称太准精值号率族维划选标写存候毛亲快效斯院查江型眼王按格养易置派层片始却专状育厂京识适属圆包火住调满县局照参红细引听该铁价严'
    
    if len(text) >= length:
        return text[:length]
    
    # If faker text is too short, supplement with common characters
    supplement = ''.join(random.choice(common_chars) for _ in range(length - len(text)))
    return text + supplement


def name():
    """Generate a random Chinese name"""
    return _faker_zh.name()


def chinese_name():
    """Generate a random Chinese name (alias for name)"""
    return name()


def sentence():
    """Generate a random sentence"""
    return _faker_en.sentence()


def chinese_sentence():
    """Generate a random Chinese sentence"""
    return _faker_zh.sentence()


def title():
    """Generate a random title"""
    return _faker_en.sentence(nb_words=random.randint(3, 8))[:-1]  # Remove period


def chinese_title():
    """Generate a random Chinese title"""
    return _faker_zh.sentence(nb_words=random.randint(3, 8))[:-1]  # Remove period


def paragraph():
    """Generate a random paragraph"""
    return _faker_en.paragraph()


def chinese_paragraph():
    """Generate a random Chinese paragraph"""
    return _faker_zh.paragraph()


def content():
    """Generate random content"""
    return '\n\n'.join(_faker_en.paragraphs(nb=random.randint(3, 6)))


def chinese_content():
    """Generate random Chinese content"""
    return '\n\n'.join(_faker_zh.paragraphs(nb=random.randint(3, 6)))


def email():
    """Generate a random email"""
    return _faker_en.email()


def url():
    """Generate a random URL"""
    return _faker_en.url()


def picker_list(data_list, num):
    """Randomly pick elements from a list"""
    if not isinstance(num, int) or num < 0:
        raise ValueError("num must be a non-negative integer")
    
    data_len = len(data_list)
    if data_len <= num:
        return data_list.copy()
    
    return random.sample(data_list, num)


def picker_dict(data_dict, num):
    """Randomly pick elements from a dictionary"""
    if not isinstance(num, int) or num < 0:
        raise ValueError("num must be a non-negative integer")
    
    data_len = len(data_dict)
    if data_len <= num:
        return data_dict.copy()
    
    # Convert dict items to list and sample
    items = list(data_dict.items())
    sampled_items = random.sample(items, num)
    return dict(sampled_items)


def date(start_date="2020-01-01", end_date="2023-12-31"):
    """Generate a random date between start_date and end_date"""
    start = datetime.strptime(start_date, "%Y-%m-%d")
    end = datetime.strptime(end_date, "%Y-%m-%d")
    delta = end - start
    random_days = random.randint(0, delta.days)
    return (start + timedelta(days=random_days)).strftime("%Y-%m-%d")


def phone_number():
    """Generate a random phone number"""
    return _faker_en.phone_number()


def chinese_phone_number():
    """Generate a random Chinese phone number"""
    return _faker_zh.phone_number()


def address():
    """Generate a random address"""
    return _faker_en.address().replace('\n', ', ')


def chinese_address():
    """Generate a random Chinese address"""
    return _faker_zh.address().replace('\n', '')


def boolean():
    """Generate a random boolean value"""
    return random.choice([True, False])


def color():
    """Generate a random color in hex format"""
    return _faker_en.hex_color()


def ip_address():
    """Generate a random IP address"""
    return _faker_en.ipv4()


# Aliases for backward compatibility
uuid = generate_uuid
int = random_int
float = random_float
time = current_time
number = random_int
ip = ip_address


if __name__ == '__main__':
    print(generate_uuid())
    print(random_int())
    print(random_float())
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