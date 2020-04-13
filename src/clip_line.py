import random

HEADER_OFFSET = const(15)
FOOTER_OFFSET = const(20)
SCREEN_WIDTH = const(320)
SCREEN_HEIGHT = const(240)

# https://en.wikipedia.org/wiki/Cohen%E2%80%93Sutherland_algorithm
INSIDE = 0
LEFT = const(1)
RIGHT = const(2)
BOTTOM = const(4)
TOP = const(8)

LOCAL_TOP = HEADER_OFFSET
LOCAL_BOTTOM = SCREEN_HEIGHT - FOOTER_OFFSET
LOCAL_RIGHT = SCREEN_WIDTH - 1
LOCAL_LEFT = 0


def compute_out_code(x, y):
    code = INSIDE
    if x < LOCAL_LEFT:
        code |= LEFT
    elif x > LOCAL_RIGHT:
        code |= RIGHT
    if y < LOCAL_TOP:
        code |= BOTTOM
    elif y > LOCAL_BOTTOM:
        code |= TOP
    return code


def clip_line(x0, y0, x1, y1):
    out_code_0 = compute_out_code(x0, y0)
    out_code_1 = compute_out_code(x1, y1)
    done = False
    count = 0
    while True:
        if count > 5:
            print("Infinite clipping loop")
            break
        count += 1
        if out_code_0 | out_code_1 == 0:
            # Everything inside
            done = True
            break
        elif out_code_0 & out_code_1 != 0:
            # Everything outside
            break
        else:
            x = 0
            y = 0
            # At least one point is outside the screen, select it
            out_code_out = out_code_1 if out_code_1 > out_code_0 else out_code_0
            if out_code_out & TOP:  # Point is above
                x = x0 + (x1 - x0) * (LOCAL_BOTTOM - y0) / (y1 - y0)
                y = LOCAL_BOTTOM
            elif out_code_out & BOTTOM:
                x = x0 + (x1 - x0) * (LOCAL_TOP - y0) / (y1 - y0)
                y = LOCAL_TOP
            elif out_code_out & RIGHT:
                y = y0 + (y1 - y0) * (LOCAL_RIGHT - x0) / (x1 - x0)
                x = LOCAL_RIGHT
            elif out_code_out & LEFT:
                y = y0 + (y1 - y0) * (LOCAL_LEFT - x0) / (x1 - x0)
                x = LOCAL_LEFT
            if out_code_out == out_code_0:
                x0 = x
                y0 = y
                out_code_0 = compute_out_code(x0, y0)
            else:
                x1 = x
                y1 = y
                out_code_1 = compute_out_code(x1, y1)
    if done:
        return int(x0), int(y0), int(x1), int(y1)
    return None, None, None, None


def extend_line(x0, y0, x1, y1):
    if x1 - x0 == 0:
        return SCREEN_WIDTH - 1, y1
    incline = (y1 - y0) / (x1 - x0)
    x1 = SCREEN_WIDTH - 1
    y1 = y0 + (x1 - x0) * incline
    return x1, y1


def random_position_along_line(x0, y0, x1, y1,text_width):
    if x1 - x0 == 0:
        incline = 0
    else:
        incline = (y1 - y0) / (x1 - x0)
    x = int(min(random.randint(x0, x1), LOCAL_RIGHT-text_width))
    y = int(y0 + (x - x0) * incline)
    return x, y

def centre_position_along_line(x0, y0, x1, y1, text_width):
    if x1 - x0 == 0:
        incline = 0
    else:
        incline = (y1 - y0) / (x1 - x0)
    x = int(min(x0 + (x1-x0)/2, LOCAL_RIGHT-text_width))
    y = int(y0 + (x - x0) * incline)
    return x, y
