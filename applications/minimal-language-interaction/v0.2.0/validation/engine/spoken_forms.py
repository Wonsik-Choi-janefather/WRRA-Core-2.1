import re

def normalize(text):
    number = {"1":"한", "2":"두", "3":"세", "4":"네", "5":"다섯"}
    text = re.sub(r"(?<!\w)([1-5])\s*시(?=에|야|예요|\s|[.!?]|$)",
                  lambda m:number[m[1]]+" 시",text)
    text = re.sub(r"(?<!\w)(한|두|세|네|다섯)\s*(잔|시)(?=만|에|야|예요|\s|[.!?]|$)", r"\1 \2", text)
    text = re.sub(r"(잔|개)\s*(주세요|부탁드려요|부탁해요)", r"\1 \2", text)
    # "시간" and "시각" are equivalent within this supported clock-time correction.
    return re.sub(r"^시간은 (?=(?:한|두|세|네|다섯) 시(?:야|예요))", "시각은 ", text)
