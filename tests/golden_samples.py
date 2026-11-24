"""Small source samples for the code-fingerprint golden tests (tests/test_fp_code.py). Do not edit casually:
changing a sample changes its pinned tokens and hashes."""

SAMPLES = {
    "lua": ("player.lua", '''-- Moth movement
local function step(t, dt)
  local n = #t  -- count
  for i = 1, n do
    t[i].x = t[i].x + t[i].vx * dt
  end
  --[[ block
  comment ]]
  return n > 0 and "moving" or 'idle'
end
'''),
    "luau": ("Lamp.luau", '''--!strict
local Lamp = {}
function Lamp.new(name: string, glow: number): typeof(Lamp)
  local self = setmetatable({}, Lamp)
  self.name = name -- label
  self.glow = glow * 0.5
  return self
end
return Lamp
'''),
    "gdscript": ("moth.gd", '''extends Node2D
# the moth
@onready var sprite = $Sprite
const TINT = Color("#fff")
var scene = preload("res://lamp.tscn")
func _process(delta):
    position.x += speed * delta  # drift
    if position.x > 640: queue_free()
'''),
    "python": ("night.py", '''# night cycle
import math
class Night:
    def __init__(self, hours=12):
        self.hours = hours  # length
        self.url = "http://example.com/#anchor"
    def tick(self, dt):
        return math.sin(self.hours * dt) > 0.5
'''),
    "csharp": ("Bell.cs", '''// bell tower
using System;
public class Bell {
    private int rings = 0; /* count */
    public void Ring(int n) {
        for (int i = 0; i < n; i++) { rings += 2; }
        Console.WriteLine("ding " + rings);
    }
}
'''),
    "minjs": ("game.min.js", 'function a(b,c){for(var d=b.length;d--;){b[d].x-=0.05;}b.tint=c.hurt?"#ff3355":"#fff";'
              'return b.speed*c.axis+b.boost}function e(f){f.speed=0;f.boost=1;f.t=[];return f}'),
}
