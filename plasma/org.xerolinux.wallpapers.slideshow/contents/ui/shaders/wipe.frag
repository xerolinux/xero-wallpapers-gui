#version 440
layout(location = 0) in vec2 qt_TexCoord0;
layout(location = 0) out vec4 fragColor;
layout(std140, binding = 0) uniform buf {
    mat4 qt_Matrix;
    float qt_Opacity;
    float progress;
};
layout(binding = 1) uniform sampler2D fromSource;
layout(binding = 2) uniform sampler2D toSource;

void main()
{
    const float softness = 0.15;
    vec2 uv = qt_TexCoord0;
    float pos = uv.x * 0.85 + (1.0 - uv.y) * 0.15;
    float edge = progress * (1.0 + softness);
    float m = smoothstep(edge - softness, edge, pos);
    fragColor = mix(texture(toSource, uv), texture(fromSource, uv), m) * qt_Opacity;
}
