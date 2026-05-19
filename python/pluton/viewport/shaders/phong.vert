#version 330 core

layout(location = 0) in vec3 in_position;
layout(location = 1) in vec3 in_normal;

uniform mat4 u_view;
uniform mat4 u_projection;
uniform mat4 u_model;

out vec3 v_world_pos;
out vec3 v_world_normal;

void main() {
    vec4 world_pos = u_model * vec4(in_position, 1.0);
    v_world_pos = world_pos.xyz;
    // Model matrix is rigid (rotation + translation) in M1, so mat3(u_model)
    // suffices for the normal. Non-uniform scaling would require a normal matrix.
    v_world_normal = mat3(u_model) * in_normal;
    gl_Position = u_projection * u_view * world_pos;
}
