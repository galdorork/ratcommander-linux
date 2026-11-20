"""Trace a mouse outline from a side photo with a transparent background.

Usage: python -I tools/trace_outline.py PHOTO.png [TOLERANCE_PX]
Prints an OUTLINE list for a side_view_data module. Needs Pillow and numpy.
"""
import sys, numpy as np
from PIL import Image, ImageFilter
alpha = Image.open(sys.argv[1]).getchannel("A").filter(ImageFilter.GaussianBlur(1.5))
m = np.asarray(alpha) > 128
H, W = m.shape
# Moore-neighbour boundary trace, starting at the top-most pixel of the leftmost column.
ys, xs = np.nonzero(m)
x0 = xs.min(); y0 = ys[xs == x0].min()
nbrs = [(-1,0),(-1,1),(0,1),(1,1),(1,0),(1,-1),(0,-1),(-1,-1)]  # (dy,dx) clockwise from N
pts = [(y0, x0)]; cur = (y0, x0); back = 6  # came from west
for _ in range(20000):
    for k in range(8):
        d = (back + 1 + k) % 8
        ny, nx = cur[0] + nbrs[d][0], cur[1] + nbrs[d][1]
        if 0 <= ny < H and 0 <= nx < W and m[ny, nx]:
            back = (d + 4) % 8
            cur = (ny, nx); break
    if cur == pts[0]: break
    pts.append(cur)
P = np.array([(x, y) for y, x in pts], float)

def rdp(p, eps):
    if len(p) < 3: return p
    a, b = p[0], p[-1]; ab = b - a; n = np.hypot(*ab) or 1
    d = np.abs(ab[0] * (p[:, 1] - a[1]) - ab[1] * (p[:, 0] - a[0])) / n
    i = d.argmax()
    if d[i] > eps:
        return np.vstack([rdp(p[:i+1], eps)[:-1], rdp(p[i:], eps)])
    return np.array([a, b])
eps = float(sys.argv[2]) if len(sys.argv) > 2 else 1.5
j = np.hypot(*(P - P[0]).T).argmax()
S = np.vstack([rdp(P[:j+1], eps)[:-1], rdp(np.vstack([P[j:], P[:1]]), eps)[:-1]])
print(len(P), "->", len(S))
print("OUTLINE = [" + ", ".join(f"({x:.0f}, {y:.0f})" for x, y in S) + "]")
