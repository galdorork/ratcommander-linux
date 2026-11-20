"""Traced geometry for the top view of the supported mouse.

Measured in a 1024 x 1024 top-down reference photo (front up). The outline was
traced from the photo's transparency mask; the main buttons, wheel and CPI
button were measured by hand. Coordinates only, no image data or logos.
The view is turned 90 degrees so the front points left, like the side view:
photo (x, y) becomes (y, 1024 - x).
"""

def _rot(points):
    return [(y, 1024 - x) for x, y in points]


def _rect(x0, y0, x1, y1):
    return [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]


OUTLINE = [(271, 641), (275, 617), (273, 602), (280, 565), (280, 519), (287, 507), (286, 501), (281, 492), (281, 444), (290, 432), (289, 428), (281, 416), (281, 367), (287, 360), (287, 356), (279, 341), (275, 302), (278, 298), (286, 298), (289, 296), (289, 198), (291, 186), (301, 163), (311, 152), (317, 152), (319, 140), (330, 130), (356, 111), (391, 90), (427, 74), (465, 62), (472, 64), (475, 68), (475, 86), (478, 89), (529, 88), (549, 90), (551, 88), (551, 72), (556, 65), (564, 64), (578, 68), (609, 80), (639, 95), (674, 117), (698, 135), (706, 143), (708, 154), (714, 155), (723, 166), (730, 179), (736, 202), (736, 269), (732, 418), (733, 514), (738, 581), (750, 666), (752, 689), (752, 717), (746, 739), (739, 746), (740, 767), (736, 785), (728, 808), (709, 845), (682, 882), (649, 917), (626, 936), (603, 949), (581, 956), (537, 961), (471, 960), (449, 957), (433, 953), (408, 941), (381, 920), (348, 885), (323, 852), (302, 815), (295, 798), (287, 770), (287, 746), (280, 741), (274, 722), (273, 691), (278, 649), (272, 645)]
OUTLINE = _rot(OUTLINE)

LEFT_BUTTON = _rot([(320, 145), (350, 120), (400, 90), (465, 64), (472, 70), (474, 407),
                    (400, 402), (327, 390), (320, 350)])
RIGHT_BUTTON = _rot([(552, 65), (560, 64), (625, 87), (675, 115), (702, 142), (702, 395),
                     (625, 400), (550, 406), (549, 80)])
WHEEL = _rot(_rect(478, 175, 544, 308))
CPI = _rot(_rect(490, 352, 530, 462))

# Wheel functions sit on labelled chips outside the body, with leader lines to
# the wheel (already in view coordinates: front left, mouse's right side up).
CHIPS = {
    19: (_rect(20, 160, 180, 222), (180, 513)),     # scroll up -> front of wheel
    17: (_rect(190, 160, 350, 222), (241, 480)),  # tilt right -> right edge
    20: (_rect(360, 160, 520, 222), (303, 513)),  # scroll down -> rear of wheel
    16: (_rect(160, 800, 320, 862), (241, 546)),    # tilt left -> left edge
}

HOTSPOTS = {13: LEFT_BUTTON, 14: RIGHT_BUTTON, 15: WHEEL, 18: CPI,
            **{n: rect for n, (rect, _) in CHIPS.items()}}

# Seam between the main buttons and the palm shell (view coordinates).
PALM_SEAM = [(395, 690), (410, 610), (418, 512), (410, 410), (395, 322)]

VIEW = (10.0, 150.0, 970.0, 760.0)   # x, y, width, height
CAPTION_Y = 870.0
