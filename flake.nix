{
  description = "SQL Language Server";
  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";

  inputs.basedpyright-nix = {
      url = "path:/home/chahak/Documents/basedpyright-nix";
      inputs.nixpkgs.follows = "nixpkgs";
  };
  inputs.poetry2nix = {
    url = "github:nix-community/poetry2nix";
    inputs.nixpkgs.follows = "nixpkgs";
  };

  outputs = { self, nixpkgs, poetry2nix, basedpyright-nix }:
    let
      systems = [ "x86_64-linux" ];
      forAllSystems = nixpkgs.lib.genAttrs systems;
      pkgs = nixpkgs.legacyPackages.x86_64-linux;
      basedpyright = basedpyright-nix.packages.x86_64-linux.default;
      inherit (poetry2nix.lib.mkPoetry2Nix { inherit pkgs; }) mkPoetryEnv;
      inherit (poetry2nix.lib.mkPoetry2Nix { inherit pkgs; }) defaultPoetryOverrides;
    in
    {
      devShells = forAllSystems (system:
        let
          pkgs = import nixpkgs {
            inherit system;
          };

          poetryEnv = mkPoetryEnv {
            projectDir = ./.;
            editablePackageSources = { pyflake = ./.; };
            python = pkgs.python312;
            overrides = defaultPoetryOverrides.extend
              (self: super: {
                sqlfluff = super.sqlfluff.overridePythonAttrs
                  (
                    old: {
                      buildInputs = (old.buildInputs or [ ]) ++ [ super.setuptools ];
                    }
                  );
              });
         };
        in
        {
          default = pkgs.mkShell { packages = [
            poetryEnv
            basedpyright
          ]; };
        });
    };
}
