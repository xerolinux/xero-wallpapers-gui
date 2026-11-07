#version 440
layout(location = 0) in vec2 qt_TexCoord0;
layout(location = 0) out vec4 fragColor;
layout(std140, binding = 0) uniform buf {
    mat4 qt_Matrix;
    float qt_Opacity;
    float progress;
    float aspect;
};
layout(binding = 1) uniform sampler2D fromSource;
layout(binding = 2) uniform sampler2D toSource;

void main()
{
    const float feather = 0.04;
    vec2 uv = qt_TexCoord0;
    float dist = length((uv - 0.5) * vec2(aspect, 1.0));
    float radius = progress * (length(vec2(aspect, 1.0)) * 0.5 + feather);
    float m = smoothstep(radius - feather, radius, dist);
    fragColor = mix(texture(toSource, uv), texture(fromSource, uv), m) * qt_Opacity;
}
