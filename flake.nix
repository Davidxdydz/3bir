{
  description = "threebir project flake";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs =
    {
      self,
      nixpkgs,
      flake-utils,
    }:
    flake-utils.lib.eachDefaultSystem (
      system:
      let
        pkgs = import nixpkgs { inherit system; };
        bir3 = pkgs.python312Packages.buildPythonApplication {
          pname = "bir3";
          version = "0.1.0";
          src = ./.;
          format = "pyproject";

          # Build dependencies
          nativeBuildInputs = [
            pkgs.makeWrapper
            pkgs.python312Packages.setuptools
            pkgs.python312Packages.wheel
          ];

          # Runtime dependencies
          propagatedBuildInputs = [
            pkgs.python312Packages.flask
            pkgs.python312Packages.flask-socketio
            pkgs.python312Packages.waitress
          ];

          # This is the magic step.
          # 1. We look for the 'waitress-serve' binary provided by the waitress package.
          # 2. We create a new binary in $out/bin named 'start-server'.
          # 3. We wrap it to execute waitress-serve with specific arguments.
          # 4. We add the current folder to PYTHONPATH so waitress can find 'app.py'
          postInstall = ''
            # Ensure site-packages exists (it should, but good practice)
            mkdir -p $out/lib/${pkgs.python312Packages.python.libPrefix}/site-packages

            # Copy templates directory if it exists
            if [ -d templates ]; then
              cp -r templates $out/lib/${pkgs.python312Packages.python.libPrefix}/site-packages/
            fi

            # Copy static directory if it exists
            if [ -d static ]; then
              cp -r static $out/lib/${pkgs.python312Packages.python.libPrefix}/site-packages/
            fi
            makeWrapper ${pkgs.python312Packages.waitress}/bin/waitress-serve $out/bin/start-server \
                --prefix PYTHONPATH : "$out/lib/${pkgs.python312Packages.python.libPrefix}/site-packages:$PYTHONPATH" \
                --add-flags "--port=8080" \
                --add-flags "app:app"
          '';
        };
      in
      {
        devShells.default = pkgs.mkShell {
          buildInputs = with pkgs; [
            (python312.withPackages (
              pp: with pp; [
                flask
                flask-socketio
                build
                waitress
              ]
            ))
            pyright
            bir3
          ];
        };
        packages = {
          default = bir3;
          dockerImage = pkgs.dockerTools.streamLayeredImage {
            name = "bir3";
            tag = "latest";
            contents = [ bir3 ];
            config = {
              Cmd = [ "${bir3}/bin/start-server" ];
              ExposedPorts = {
                "8080/tcp" = { };
              };
            };
          };
        };

        apps.default = {
          type = "app";
          program = "${bir3}/bin/start-server";
        };
      }
    );
}
