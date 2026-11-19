{ inputs, pkgs, ... }:
{
  home.packages = [
    inputs.hermes-agent.packages.${pkgs.system}.default
    inputs.hermes-agent.packages.${pkgs.system}.desktop
  ];
}
