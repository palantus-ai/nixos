{
  inputs,
  lib,
  pkgs,
  osConfig,
  ...
}:
{
  imports = [
    ./scripts.nix
  ];
  home = {
    packages = with pkgs; [
      niri
      xwayland-satellite # xwayland support
    ];
    file =
      let
        hostPath = "hosts/nixos/${osConfig.hostSpec.hostName}/niri";
        hostMonitorOffPath = lib.custom.relativeToRoot "${hostPath}/monitor-off.kdl";
        monitorOffConfig = if lib.pathExists hostMonitorOffPath then hostMonitorOffPath else ./monitor-off.kdl;
        finalConfig =
          lib.flatten [
            # order matters
            ./inputs.kdl
            (map lib.custom.relativeToRoot [
              "${hostPath}/outputs.kdl"
              "${hostPath}/workspaces.kdl"
              "${hostPath}/startup.kdl"
            ])
            (builtins.replaceStrings
              [ "#MONITOR_OFF_BINDING#" ]
              [ (lib.readFile monitorOffConfig) ]
              (lib.readFile ./binds.kdl)
            )
            ./rules.kdl
            ./config.kdl
          ]
          |> lib.concatMapStringsSep "\n" (file: if builtins.isPath file then lib.readFile file else file);
      in
      {
        ".config/niri/config.kdl".text = finalConfig;
        ".config/niri/animations/" = {
          source = ./animations;
          recursive = true;
        };
      };
  };
}
