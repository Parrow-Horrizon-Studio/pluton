#version 330 core

layout(location = 0) in vec3 in_position;
layout(location = 1) in vec3 in_normal;
// M7.5b — BOTH sides' texture coordinates, baked per corner at upload time.
// Two attributes rather than one because culling is disabled: both sides of a
// face reach the fragment shader in a single draw call selected by
// gl_FrontFacing, so a single UV would make the back's independent placement
// (spec D7, 1.4) physically unrepresentable.
layout(location = 2) in vec2 in_uv;
layout(location = 3) in vec2 in_uv_back;

uniform mat4 u_view;
uniform mat4 u_projection;
uniform mat4 u_model;

out vec3 v_world_pos;
out vec3 v_world_normal;
out vec2 v_uv;
out vec2 v_uv_back;

void main() {
    vec4 world_pos = u_model * vec4(in_position, 1.0);
    v_world_pos = world_pos.xyz;
    // Use inverse-transpose of mat3(u_model) as the normal matrix so normals
    // transform correctly under non-uniform scale (M4e Scale tool).
    // transpose(inverse()) equals mat3(u_model) for rotation-only/uniform-scale
    // transforms, so existing scenes are unaffected.
    mat3 normal_matrix = transpose(inverse(mat3(u_model)));
    v_world_normal = normalize(normal_matrix * in_normal);
    v_uv = in_uv;
    v_uv_back = in_uv_back;
    gl_Position = u_projection * u_view * world_pos;
}
