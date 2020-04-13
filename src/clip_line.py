HEADER_OFFSET = const(20)
FOOTER_OFFSET = const(20)
SCREEN_WIDTH = const(320)
SCREEN_HEIGHT = const(240)

# https://en.wikipedia.org/wiki/Cohen%E2%80%93Sutherland_algorithm
INSIDE = 0
LEFT = const(1)
RIGHT = const(2)
BOTTOM = const(4)
TOP = const(8)


def compute_out_code(x, y):
    code = INSIDE
    if x < 0:
        code |= LEFT
    elif x >= SCREEN_WIDTH:
        code |= RIGHT
    if y < HEADER_OFFSET:
        code |= BOTTOM
    elif y >= SCREEN_HEIGHT - FOOTER_OFFSET:
        code |= TOP
    return code


def clip_line(x0, y0, x1, y1):
    out_code_0 = compute_out_code(x0, y0)
    out_code_1 = compute_out_code(x1, y1)
    done = False
    while True:
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
                x = x0 + (x1 - x0) * (SCREEN_HEIGHT - y0 - FOOTER_OFFSET) / (y1 - y0)
                y = SCREEN_HEIGHT - FOOTER_OFFSET
            elif out_code_out & BOTTOM:
                x = x0 + (x1 - x0) * (HEADER_OFFSET - y0) / (y1 - y0)
                y = HEADER_OFFSET
            elif out_code_out & RIGHT:
                y = y0 + (y1 - y0) * (SCREEN_WIDTH - x0 - 1) / (x1 - x0)
                x = SCREEN_WIDTH - 1
            elif out_code_out & LEFT:
                y = y0 + (y1 - y0) * (HEADER_OFFSET - x0) / (x1 - x0)
                x = 0
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
