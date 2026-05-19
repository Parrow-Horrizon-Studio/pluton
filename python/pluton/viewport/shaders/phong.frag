#version 330 core

in vec3 v_world_pos;
in vec3 v_world_normal;
out vec4 frag_color;

uniform vec3 u_camera_pos;

// Hardcoded for M1 — surfaced as uniforms now so the python side can tweak
// them, and so the M5 material system has a natural plug-in point.
uniform vec3  u_light_dir;        // direction the light travels (unit length)
uniform vec3  u_light_color;
uniform vec3  u_material_ambient;
uniform vec3  u_material_diffuse;
uniform vec3  u_material_specular;
uniform float u_material_shininess;

void main() {
    vec3 N = normalize(v_world_normal);
    // Convention: `u_light_dir` is the direction the light *travels* (incident
    // ray pointing INTO the surface). So `L` is the incident ray, `-L` points
    // from surface to light, and `reflect(L, N)` gives the bounce direction.
    vec3 L = normalize(u_light_dir);
    vec3 V = normalize(u_camera_pos - v_world_pos);
    vec3 R = reflect(L, N);  // bounce direction (away from surface)

    float diff = max(dot(N, -L), 0.0);
    float spec = pow(max(dot(R, V), 0.0), u_material_shininess);

    vec3 color = u_material_ambient
               + u_material_diffuse  * diff * u_light_color
               + u_material_specular * spec * u_light_color;

    frag_color = vec4(color, 1.0);
}
