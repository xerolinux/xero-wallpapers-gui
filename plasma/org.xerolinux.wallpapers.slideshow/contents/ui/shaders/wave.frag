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
    vec2 uv = qt_TexCoord0;
    float dist = uv.x - (progress * 1.4 - 0.2);
    float amp = 0.025 * sin(progress * 3.14159265);
    float ripple = sin(dist * 40.0 - progress * 12.0) * amp * exp(-abs(dist) * 5.0);
    vec2 duv = clamp(uv + vec2(ripple * 0.5, ripple), 0.0, 1.0);
    float m = smoothstep(-0.1, 0.1, dist);
    fragColor = mix(texture(toSource, duv), texture(fromSource, duv), m) * qt_Opacity;
}
