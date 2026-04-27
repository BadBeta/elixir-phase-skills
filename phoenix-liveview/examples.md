# Phoenix LiveView Examples & Anti-Patterns

## Complete LiveView with All Callbacks

```elixir
defmodule MyAppWeb.PostLive.Index do
  use MyAppWeb, :live_view

  alias MyApp.Blog

  @impl true
  def mount(_params, _session, socket) do
    if connected?(socket) do
      Blog.subscribe()
    end

    {:ok,
     socket
     |> assign(:page_title, "Posts")
     |> stream(:posts, Blog.list_posts())}
  end

  @impl true
  def handle_params(params, _uri, socket) do
    {:noreply, apply_action(socket, socket.assigns.live_action, params)}
  end

  defp apply_action(socket, :index, _params) do
    assign(socket, :post, nil)
  end

  defp apply_action(socket, :new, _params) do
    assign(socket, :post, %Post{})
  end

  defp apply_action(socket, :edit, %{"id" => id}) do
    assign(socket, :post, Blog.get_post!(id))
  end

  @impl true
  def render(assigns) do
    ~H"""
    <Layouts.app flash={@flash}>
      <.header>
        Posts
        <:actions>
          <.link patch={~p"/posts/new"}>
            <.button>New Post</.button>
          </.link>
        </:actions>
      </.header>

      <div id="posts" phx-update="stream">
        <div :for={{dom_id, post} <- @streams.posts} id={dom_id} class="border-b py-4">
          <h3 class="font-bold">{post.title}</h3>
          <p class="text-gray-600">{post.body}</p>
          <div class="mt-2 space-x-2">
            <.link patch={~p"/posts/#{post}/edit"}>Edit</.link>
            <.link phx-click="delete" phx-value-id={post.id} data-confirm="Are you sure?">
              Delete
            </.link>
          </div>
        </div>
      </div>

      <.modal :if={@live_action in [:new, :edit]} id="post-modal" show on_cancel={JS.patch(~p"/posts")}>
        <.live_component
          module={MyAppWeb.PostLive.FormComponent}
          id={@post.id || :new}
          title={@page_title}
          action={@live_action}
          post={@post}
          patch={~p"/posts"}
        />
      </.modal>
    </Layouts.app>
    """
  end

  @impl true
  def handle_event("delete", %{"id" => id}, socket) do
    post = Blog.get_post!(id)
    {:ok, _} = Blog.delete_post(post)
    {:noreply, stream_delete(socket, :posts, post)}
  end

  @impl true
  def handle_info({:post_created, post}, socket) do
    {:noreply, stream_insert(socket, :posts, post, at: 0)}
  end

  def handle_info({:post_updated, post}, socket) do
    {:noreply, stream_insert(socket, :posts, post)}
  end

  def handle_info({:post_deleted, post}, socket) do
    {:noreply, stream_delete(socket, :posts, post)}
  end
end
```

## LiveComponent with Events

```elixir
defmodule MyAppWeb.PostLive.FormComponent do
  use MyAppWeb, :live_component

  alias MyApp.Blog

  @impl true
  def update(%{post: post} = assigns, socket) do
    changeset = Blog.change_post(post)

    {:ok,
     socket
     |> assign(assigns)
     |> assign(:form, to_form(changeset))}
  end

  @impl true
  def render(assigns) do
    ~H"""
    <div>
      <.header>
        {@title}
        <:subtitle>Manage post details</:subtitle>
      </.header>

      <.form
        for={@form}
        id="post-form"
        phx-target={@myself}
        phx-change="validate"
        phx-submit="save"
      >
        <.input field={@form[:title]} type="text" label="Title" />
        <.input field={@form[:body]} type="textarea" label="Body" rows={6} />
        <.input field={@form[:published]} type="checkbox" label="Published" />

        <:actions>
          <.button phx-disable-with="Saving...">Save Post</.button>
        </:actions>
      </.form>
    </div>
    """
  end

  @impl true
  def handle_event("validate", %{"post" => post_params}, socket) do
    changeset =
      socket.assigns.post
      |> Blog.change_post(post_params)
      |> Map.put(:action, :validate)

    {:noreply, assign(socket, :form, to_form(changeset))}
  end

  def handle_event("save", %{"post" => post_params}, socket) do
    save_post(socket, socket.assigns.action, post_params)
  end

  defp save_post(socket, :new, post_params) do
    case Blog.create_post(post_params) do
      {:ok, _post} ->
        {:noreply,
         socket
         |> put_flash(:info, "Post created successfully")
         |> push_patch(to: socket.assigns.patch)}

      {:error, %Ecto.Changeset{} = changeset} ->
        {:noreply, assign(socket, :form, to_form(changeset))}
    end
  end

  defp save_post(socket, :edit, post_params) do
    case Blog.update_post(socket.assigns.post, post_params) do
      {:ok, _post} ->
        {:noreply,
         socket
         |> put_flash(:info, "Post updated successfully")
         |> push_patch(to: socket.assigns.patch)}

      {:error, %Ecto.Changeset{} = changeset} ->
        {:noreply, assign(socket, :form, to_form(changeset))}
    end
  end
end
```

## Form with Validation

```elixir
defmodule MyAppWeb.UserLive.Registration do
  use MyAppWeb, :live_view

  alias MyApp.Accounts
  alias MyApp.Accounts.User

  def mount(_params, _session, socket) do
    changeset = Accounts.change_user_registration(%User{})

    {:ok,
     socket
     |> assign(:page_title, "Register")
     |> assign(:form, to_form(changeset))
     |> assign(:trigger_submit, false)}
  end

  def render(assigns) do
    ~H"""
    <Layouts.app flash={@flash}>
      <div class="max-w-md mx-auto">
        <.header>Create Account</.header>

        <.form
          for={@form}
          id="registration-form"
          phx-change="validate"
          phx-submit="save"
          phx-trigger-action={@trigger_submit}
          action={~p"/users/log_in?_action=registered"}
          method="post"
        >
          <.input field={@form[:email]} type="email" label="Email" required />
          <.input field={@form[:password]} type="password" label="Password" required />
          <.input
            field={@form[:password_confirmation]}
            type="password"
            label="Confirm Password"
            required
          />

          <:actions>
            <.button class="w-full" phx-disable-with="Creating account...">
              Create Account
            </.button>
          </:actions>
        </.form>

        <p class="mt-4 text-center text-sm">
          Already have an account?
          <.link navigate={~p"/users/log_in"} class="font-semibold text-brand hover:underline">
            Sign in
          </.link>
        </p>
      </div>
    </Layouts.app>
    """
  end

  def handle_event("validate", %{"user" => user_params}, socket) do
    changeset =
      %User{}
      |> Accounts.change_user_registration(user_params)
      |> Map.put(:action, :validate)

    {:noreply, assign(socket, :form, to_form(changeset))}
  end

  def handle_event("save", %{"user" => user_params}, socket) do
    case Accounts.register_user(user_params) do
      {:ok, user} ->
        {:ok, _} = Accounts.deliver_user_confirmation_instructions(user)

        {:noreply,
         socket
         |> assign(:trigger_submit, true)
         |> assign(:form, to_form(Accounts.change_user_registration(user, user_params)))}

      {:error, %Ecto.Changeset{} = changeset} ->
        {:noreply, assign(socket, :form, to_form(changeset))}
    end
  end
end
```

## Stream Implementation

```elixir
defmodule MyAppWeb.ChatLive do
  use MyAppWeb, :live_view

  alias MyApp.Chat

  def mount(%{"room_id" => room_id}, _session, socket) do
    if connected?(socket) do
      Chat.subscribe(room_id)
    end

    messages = Chat.list_messages(room_id, limit: 50)

    {:ok,
     socket
     |> assign(:room_id, room_id)
     |> assign(:form, to_form(%{"body" => ""}))
     |> stream(:messages, messages)}
  end

  def render(assigns) do
    ~H"""
    <Layouts.app flash={@flash}>
      <div class="flex flex-col h-[80vh]">
        <div id="messages" phx-update="stream" class="flex-1 overflow-y-auto p-4 space-y-2">
          <div
            :for={{dom_id, message} <- @streams.messages}
            id={dom_id}
            class={[
              "p-3 rounded-lg max-w-[80%]",
              message.user_id == @current_user.id && "ml-auto bg-blue-100",
              message.user_id != @current_user.id && "bg-gray-100"
            ]}
          >
            <div class="text-sm font-semibold">{message.user.name}</div>
            <div>{message.body}</div>
            <div class="text-xs text-gray-500">{format_time(message.inserted_at)}</div>
          </div>
        </div>

        <.form for={@form} phx-submit="send" class="p-4 border-t">
          <div class="flex gap-2">
            <.input
              field={@form[:body]}
              type="text"
              placeholder="Type a message..."
              class="flex-1"
              autocomplete="off"
            />
            <.button type="submit" phx-disable-with="Sending...">Send</.button>
          </div>
        </.form>
      </div>
    </Layouts.app>
    """
  end

  def handle_event("send", %{"body" => body}, socket) when body != "" do
    case Chat.create_message(socket.assigns.room_id, socket.assigns.current_user, body) do
      {:ok, _message} ->
        {:noreply, assign(socket, :form, to_form(%{"body" => ""}))}

      {:error, _changeset} ->
        {:noreply, put_flash(socket, :error, "Failed to send message")}
    end
  end

  def handle_event("send", _, socket), do: {:noreply, socket}

  def handle_info({:new_message, message}, socket) do
    message = Chat.preload_user(message)
    {:noreply, stream_insert(socket, :messages, message)}
  end

  defp format_time(datetime) do
    Calendar.strftime(datetime, "%H:%M")
  end
end
```

## File Upload (Local and S3)

### Local Upload

```elixir
defmodule MyAppWeb.AvatarLive do
  use MyAppWeb, :live_view

  def mount(_params, _session, socket) do
    {:ok,
     socket
     |> assign(:uploaded_files, [])
     |> allow_upload(:avatar,
         accept: ~w(.jpg .jpeg .png),
         max_entries: 1,
         max_file_size: 5_000_000
       )}
  end

  def render(assigns) do
    ~H"""
    <Layouts.app flash={@flash}>
      <form phx-submit="save" phx-change="validate">
        <.live_file_input upload={@uploads.avatar} />

        <div :for={entry <- @uploads.avatar.entries} class="mt-4">
          <.live_img_preview entry={entry} class="w-32 h-32 object-cover rounded" />

          <div class="flex items-center gap-2 mt-2">
            <progress value={entry.progress} max="100" class="flex-1">
              {entry.progress}%
            </progress>
            <button
              type="button"
              phx-click="cancel"
              phx-value-ref={entry.ref}
              class="text-red-500"
            >
              Cancel
            </button>
          </div>

          <div :for={err <- upload_errors(@uploads.avatar, entry)} class="text-red-500 text-sm">
            {error_to_string(err)}
          </div>
        </div>

        <div :for={err <- upload_errors(@uploads.avatar)} class="text-red-500 text-sm">
          {error_to_string(err)}
        </div>

        <.button type="submit" class="mt-4" disabled={@uploads.avatar.entries == []}>
          Upload
        </.button>
      </form>

      <div :if={@uploaded_files != []} class="mt-8">
        <h3 class="font-bold">Uploaded:</h3>
        <div :for={file <- @uploaded_files} class="mt-2">
          <img src={file} class="w-32 h-32 object-cover rounded" />
        </div>
      </div>
    </Layouts.app>
    """
  end

  def handle_event("validate", _params, socket) do
    {:noreply, socket}
  end

  def handle_event("cancel", %{"ref" => ref}, socket) do
    {:noreply, cancel_upload(socket, :avatar, ref)}
  end

  def handle_event("save", _params, socket) do
    uploaded_files =
      consume_uploaded_entries(socket, :avatar, fn %{path: path}, entry ->
        dest = Path.join(["priv/static/uploads", "#{entry.uuid}-#{entry.client_name}"])
        File.mkdir_p!(Path.dirname(dest))
        File.cp!(path, dest)
        {:ok, ~p"/uploads/#{Path.basename(dest)}"}
      end)

    {:noreply, update(socket, :uploaded_files, &(&1 ++ uploaded_files))}
  end

  defp error_to_string(:too_large), do: "File too large (max 5MB)"
  defp error_to_string(:not_accepted), do: "Invalid file type"
  defp error_to_string(:too_many_files), do: "Too many files"
  defp error_to_string(err), do: inspect(err)
end
```

### S3 External Upload

```elixir
defmodule MyAppWeb.S3UploadLive do
  use MyAppWeb, :live_view

  def mount(_params, _session, socket) do
    {:ok,
     socket
     |> allow_upload(:photos,
         accept: ~w(.jpg .jpeg .png .gif),
         max_entries: 5,
         max_file_size: 10_000_000,
         external: &presign_upload/2
       )}
  end

  defp presign_upload(entry, socket) do
    key = "uploads/#{entry.uuid}-#{entry.client_name}"

    config = ExAws.Config.new(:s3)

    {:ok, url} =
      ExAws.S3.presigned_url(config, :put, "my-bucket", key,
        expires_in: 3600,
        query_params: [{"Content-Type", entry.client_type}]
      )

    {:ok, %{uploader: "S3", key: key, url: url}, socket}
  end

  # ... rest similar to local upload
end
```

### Directory Upload with Zip Compression

Upload entire directories by compressing client-side with JSZip and extracting server-side:

**JavaScript Hook (app.js):**

```javascript
import JSZip from "jszip"

Hooks.DirectoryUpload = {
  mounted() {
    this.el.addEventListener("change", async (e) => {
      const files = Array.from(e.target.files)
      if (files.length === 0) return

      // Show progress indicator
      this.pushEvent("zip_started", { file_count: files.length })

      const zip = new JSZip()

      // Add all files preserving directory structure
      for (const file of files) {
        const path = file.webkitRelativePath || file.name
        zip.file(path, file, { binary: true })
      }

      try {
        const blob = await zip.generateAsync({
          type: "blob",
          compression: "DEFLATE",
          compressionOptions: { level: 6 }
        }, (metadata) => {
          // Report compression progress
          this.pushEvent("zip_progress", { percent: Math.round(metadata.percent) })
        })

        // Trigger LiveView upload with compressed blob
        this.upload("directory", [blob])
      } catch (error) {
        this.pushEvent("zip_error", { message: error.message })
      }
    })
  }
}
```

**LiveView Module:**

```elixir
defmodule MyAppWeb.DirectoryUploadLive do
  use MyAppWeb, :live_view

  @uploads_dir Path.join([:code.priv_dir(:my_app), "static", "uploads"])

  def mount(_params, _session, socket) do
    File.mkdir_p!(@uploads_dir)

    {:ok,
     socket
     |> assign(:zip_progress, nil)
     |> assign(:upload_progress, 0)
     |> assign(:extracted_files, [])
     |> assign(:error, nil)
     |> allow_upload(:directory,
         accept: :any,
         max_entries: 1,
         max_file_size: 500_000_000,  # 500MB
         auto_upload: true,
         progress: &handle_progress/3
       )}
  end

  def render(assigns) do
    ~H"""
    <Layouts.app flash={@flash}>
      <div class="max-w-xl mx-auto space-y-6">
        <h1 class="text-2xl font-bold">Directory Upload</h1>

        <%!-- Hidden LiveView upload input --%>
        <.live_file_input upload={@uploads.directory} class="hidden" />

        <%!-- Custom directory picker with hook --%>
        <div class="border-2 border-dashed border-gray-300 rounded-lg p-8 text-center">
          <input
            type="file"
            id="directory-input"
            phx-hook="DirectoryUpload"
            webkitdirectory={true}
            class="hidden"
          />
          <label
            for="directory-input"
            class="cursor-pointer text-blue-600 hover:text-blue-800"
          >
            <.icon name="hero-folder-open" class="w-12 h-12 mx-auto mb-2" />
            <span class="text-lg">Select a folder to upload</span>
          </label>
        </div>

        <%!-- Compression progress --%>
        <div :if={@zip_progress} class="space-y-2">
          <div class="text-sm text-gray-600">Compressing files...</div>
          <div class="w-full bg-gray-200 rounded-full h-2">
            <div
              class="bg-yellow-500 h-2 rounded-full transition-all"
              style={"width: #{@zip_progress}%"}
            />
          </div>
        </div>

        <%!-- Upload progress --%>
        <div :if={@upload_progress > 0 and @upload_progress < 100} class="space-y-2">
          <div class="text-sm text-gray-600">Uploading...</div>
          <div class="w-full bg-gray-200 rounded-full h-2">
            <div
              class="bg-blue-500 h-2 rounded-full transition-all"
              style={"width: #{@upload_progress}%"}
            />
          </div>
        </div>

        <%!-- Error display --%>
        <div :if={@error} class="p-4 bg-red-100 text-red-700 rounded">
          {@error}
        </div>

        <%!-- Extracted files --%>
        <div :if={@extracted_files != []} class="space-y-2">
          <h2 class="font-semibold">Extracted Files:</h2>
          <ul class="text-sm text-gray-600 max-h-64 overflow-y-auto">
            <li :for={file <- @extracted_files} class="truncate">
              <.icon name="hero-document" class="w-4 h-4 inline" />
              {file}
            </li>
          </ul>
        </div>
      </div>
    </Layouts.app>
    """
  end

  # Handle compression progress from JS
  def handle_event("zip_started", %{"file_count" => count}, socket) do
    {:noreply, assign(socket, zip_progress: 0, error: nil)}
  end

  def handle_event("zip_progress", %{"percent" => percent}, socket) do
    {:noreply, assign(socket, zip_progress: percent)}
  end

  def handle_event("zip_error", %{"message" => message}, socket) do
    {:noreply, assign(socket, error: "Compression failed: #{message}", zip_progress: nil)}
  end

  # Handle upload progress
  defp handle_progress(:directory, entry, socket) do
    socket = assign(socket, :upload_progress, entry.progress)

    if entry.done? do
      socket = assign(socket, zip_progress: nil)

      case consume_uploaded_entries(socket, :directory, &extract_zip/2) do
        [{:ok, files}] ->
          {:noreply, assign(socket, extracted_files: files, upload_progress: 100)}

        [{:error, reason}] ->
          {:noreply, assign(socket, error: "Extraction failed: #{reason}")}
      end
    else
      {:noreply, socket}
    end
  end

  defp extract_zip(%{path: temp_path}, _entry) do
    # Security: Validate zip contents before extraction
    case :zip.list_dir(~c"#{temp_path}") do
      {:ok, file_list} ->
        # Check for path traversal attacks
        files = extract_file_names(file_list)

        if Enum.any?(files, &path_traversal?/1) do
          {:error, "Invalid file paths detected"}
        else
          case :zip.unzip(~c"#{temp_path}", cwd: ~c"#{@uploads_dir}") do
            {:ok, extracted} ->
              {:ok, Enum.map(extracted, &to_string/1)}

            {:error, reason} ->
              {:error, inspect(reason)}
          end
        end

      {:error, reason} ->
        {:error, inspect(reason)}
    end
  end

  defp extract_file_names(file_list) do
    file_list
    |> Enum.filter(fn
      {:zip_file, _, _, _, _, _} -> true
      _ -> false
    end)
    |> Enum.map(fn {:zip_file, name, _, _, _, _} -> to_string(name) end)
  end

  defp path_traversal?(path) do
    String.contains?(path, "..") or String.starts_with?(path, "/")
  end
end
```

**Installation:**

```bash
cd assets && npm install jszip
```

**Security Considerations:**
- Always validate zip contents before extraction
- Check for path traversal attacks (`..` in paths)
- Limit maximum file size and count
- Consider scanning for malicious files
- Run extraction in isolated directory

## JavaScript Hook

### Infinite Scroll

```elixir
defmodule MyAppWeb.FeedLive do
  use MyAppWeb, :live_view

  def mount(_params, _session, socket) do
    {:ok,
     socket
     |> assign(:page, 1)
     |> assign(:end_of_feed, false)
     |> stream(:posts, load_posts(1))}
  end

  def render(assigns) do
    ~H"""
    <Layouts.app flash={@flash}>
      <div id="posts" phx-update="stream">
        <div :for={{dom_id, post} <- @streams.posts} id={dom_id} class="border-b p-4">
          <h3>{post.title}</h3>
          <p>{post.body}</p>
        </div>
      </div>

      <div
        :if={!@end_of_feed}
        id="infinite-scroll-trigger"
        phx-hook="InfiniteScroll"
        phx-update="ignore"
        class="h-20 flex items-center justify-center"
      >
        <span class="loading">Loading more...</span>
      </div>
    </Layouts.app>
    """
  end

  def handle_event("load_more", _, socket) do
    if socket.assigns.end_of_feed do
      {:noreply, socket}
    else
      page = socket.assigns.page + 1
      posts = load_posts(page)

      socket =
        if posts == [] do
          assign(socket, :end_of_feed, true)
        else
          socket
          |> assign(:page, page)
          |> stream(:posts, posts)
        end

      {:noreply, socket}
    end
  end

  defp load_posts(page, per_page \\ 20) do
    Blog.list_posts(page: page, per_page: per_page)
  end
end
```

```javascript
// app.js
let Hooks = {}

Hooks.InfiniteScroll = {
  mounted() {
    this.observer = new IntersectionObserver(
      (entries) => {
        const entry = entries[0]
        if (entry.isIntersecting) {
          this.pushEvent("load_more", {})
        }
      },
      { rootMargin: "200px" }
    )
    this.observer.observe(this.el)
  },

  destroyed() {
    this.observer.disconnect()
  }
}

let liveSocket = new LiveSocket("/live", Socket, {
  hooks: Hooks,
  params: { _csrf_token: csrfToken }
})
```

### Chart Hook

```elixir
def render(assigns) do
  ~H"""
  <div
    id="sales-chart"
    phx-hook="Chart"
    phx-update="ignore"
    data-chart-data={Jason.encode!(@chart_data)}
    class="h-64"
  />
  """
end

def handle_event("update_range", %{"range" => range}, socket) do
  chart_data = calculate_chart_data(range)

  {:noreply,
   socket
   |> assign(:chart_data, chart_data)
   |> push_event("chart:update", %{data: chart_data})}
end
```

```javascript
import Chart from "chart.js/auto"

Hooks.Chart = {
  mounted() {
    const data = JSON.parse(this.el.dataset.chartData)
    this.chart = new Chart(this.el, {
      type: "line",
      data: data
    })

    this.handleEvent("chart:update", ({ data }) => {
      this.chart.data = data
      this.chart.update()
    })
  },

  destroyed() {
    this.chart.destroy()
  }
}
```

## PubSub Real-Time Updates

```elixir
defmodule MyAppWeb.DashboardLive do
  use MyAppWeb, :live_view

  alias MyApp.Stats

  def mount(_params, _session, socket) do
    if connected?(socket) do
      :timer.send_interval(5000, self(), :refresh_stats)
      Phoenix.PubSub.subscribe(MyApp.PubSub, "orders")
      Phoenix.PubSub.subscribe(MyApp.PubSub, "users")
    end

    {:ok,
     socket
     |> assign(:stats, Stats.get_dashboard_stats())
     |> stream(:recent_orders, Stats.recent_orders(limit: 10))}
  end

  def render(assigns) do
    ~H"""
    <Layouts.app flash={@flash}>
      <div class="grid grid-cols-3 gap-4 mb-8">
        <.stat_card title="Total Orders" value={@stats.total_orders} />
        <.stat_card title="Revenue" value={format_currency(@stats.revenue)} />
        <.stat_card title="Active Users" value={@stats.active_users} />
      </div>

      <h2 class="text-xl font-bold mb-4">Recent Orders</h2>
      <div id="orders" phx-update="stream">
        <div
          :for={{dom_id, order} <- @streams.recent_orders}
          id={dom_id}
          class="border-b py-2 flex justify-between"
        >
          <span>Order #{order.id}</span>
          <span>{format_currency(order.total)}</span>
        </div>
      </div>
    </Layouts.app>
    """
  end

  def handle_info(:refresh_stats, socket) do
    {:noreply, assign(socket, :stats, Stats.get_dashboard_stats())}
  end

  def handle_info({:order_created, order}, socket) do
    {:noreply,
     socket
     |> update(:stats, fn stats ->
       %{stats | total_orders: stats.total_orders + 1, revenue: stats.revenue + order.total}
     end)
     |> stream_insert(:recent_orders, order, at: 0, limit: 10)}
  end

  def handle_info({:user_active, _user}, socket) do
    {:noreply,
     update(socket, :stats, fn stats ->
       %{stats | active_users: stats.active_users + 1}
     end)}
  end

  defp format_currency(amount), do: "$#{:erlang.float_to_binary(amount / 100, decimals: 2)}"
end
```

## Modal Component

```elixir
attr :id, :string, required: true
attr :show, :boolean, default: false
attr :on_cancel, JS, default: %JS{}

slot :inner_block, required: true

def modal(assigns) do
  ~H"""
  <div
    id={@id}
    phx-mounted={@show && show_modal(@id)}
    phx-remove={hide_modal(@id)}
    data-cancel={JS.exec(@on_cancel, "phx-remove")}
    class="relative z-50 hidden"
  >
    <div id={"#{@id}-bg"} class="fixed inset-0 bg-black/50 transition-opacity" aria-hidden="true" />

    <div class="fixed inset-0 overflow-y-auto" role="dialog" aria-modal="true">
      <div class="flex min-h-full items-center justify-center p-4">
        <div
          id={"#{@id}-container"}
          phx-click-away={JS.exec("data-cancel", to: "##{@id}")}
          phx-window-keydown={JS.exec("data-cancel", to: "##{@id}")}
          phx-key="escape"
          class="relative bg-white rounded-lg shadow-xl max-w-lg w-full p-6"
        >
          <button
            type="button"
            phx-click={JS.exec("data-cancel", to: "##{@id}")}
            class="absolute top-4 right-4 text-gray-400 hover:text-gray-600"
            aria-label="close"
          >
            <.icon name="hero-x-mark" class="w-5 h-5" />
          </button>

          {render_slot(@inner_block)}
        </div>
      </div>
    </div>
  </div>
  """
end

defp show_modal(id) do
  %JS{}
  |> JS.show(to: "##{id}")
  |> JS.show(to: "##{id}-bg", transition: {"ease-out duration-300", "opacity-0", "opacity-100"})
  |> JS.show(
    to: "##{id}-container",
    transition: {"ease-out duration-300", "opacity-0 scale-95", "opacity-100 scale-100"}
  )
  |> JS.focus_first(to: "##{id}-container")
end

defp hide_modal(id) do
  %JS{}
  |> JS.hide(to: "##{id}-bg", transition: {"ease-in duration-200", "opacity-100", "opacity-0"})
  |> JS.hide(
    to: "##{id}-container",
    transition: {"ease-in duration-200", "opacity-100 scale-100", "opacity-0 scale-95"}
  )
  |> JS.hide(to: "##{id}", transition: {"block", "block", "hidden"})
  |> JS.pop_focus()
end
```

## Search with Debounce

```elixir
defmodule MyAppWeb.SearchLive do
  use MyAppWeb, :live_view

  alias MyApp.Search

  def mount(_params, _session, socket) do
    {:ok,
     socket
     |> assign(:query, "")
     |> assign(:results, [])
     |> assign(:loading, false)}
  end

  def handle_params(%{"q" => query}, _uri, socket) when query != "" do
    {:noreply,
     socket
     |> assign(:query, query)
     |> assign(:loading, true)
     |> start_async(:search, fn -> Search.perform(query) end)}
  end

  def handle_params(_params, _uri, socket) do
    {:noreply, assign(socket, query: "", results: [], loading: false)}
  end

  def render(assigns) do
    ~H"""
    <Layouts.app flash={@flash}>
      <form phx-change="search" phx-submit="search">
        <.input
          type="search"
          name="q"
          value={@query}
          placeholder="Search..."
          phx-debounce="300"
          autocomplete="off"
        />
      </form>

      <div :if={@loading} class="mt-4 text-gray-500">
        Searching...
      </div>

      <div :if={!@loading && @query != "" && @results == []} class="mt-4 text-gray-500">
        No results found
      </div>

      <ul :if={@results != []} class="mt-4 space-y-2">
        <li :for={result <- @results} class="border-b pb-2">
          <.link navigate={result.url} class="hover:text-blue-600">
            {result.title}
          </.link>
        </li>
      </ul>
    </Layouts.app>
    """
  end

  def handle_event("search", %{"q" => query}, socket) do
    {:noreply, push_patch(socket, to: ~p"/search?q=#{query}")}
  end

  def handle_async(:search, {:ok, results}, socket) do
    {:noreply, assign(socket, results: results, loading: false)}
  end

  def handle_async(:search, {:exit, _reason}, socket) do
    {:noreply,
     socket
     |> assign(:loading, false)
     |> put_flash(:error, "Search failed")}
  end
end
```

## Interactive SVG Graphics

### Clickable SVG Elements

```elixir
defmodule MyAppWeb.FloorPlanLive do
  use MyAppWeb, :live_view

  def mount(_params, _session, socket) do
    rooms = [
      %{id: "room-1", name: "Living Room", x: 10, y: 10, width: 200, height: 150, status: :available},
      %{id: "room-2", name: "Kitchen", x: 220, y: 10, width: 150, height: 150, status: :occupied},
      %{id: "room-3", name: "Bedroom", x: 10, y: 170, width: 150, height: 120, status: :available}
    ]

    {:ok,
     socket
     |> assign(:rooms, rooms)
     |> assign(:selected_room, nil)}
  end

  def render(assigns) do
    ~H"""
    <Layouts.app flash={@flash}>
      <div class="flex gap-8">
        <svg viewBox="0 0 400 320" class="w-full max-w-lg border rounded">
          <rect
            :for={room <- @rooms}
            id={room.id}
            x={room.x}
            y={room.y}
            width={room.width}
            height={room.height}
            phx-click="select_room"
            phx-value-id={room.id}
            class={[
              "cursor-pointer transition-colors",
              room.status == :available && "fill-green-200 hover:fill-green-300",
              room.status == :occupied && "fill-red-200 hover:fill-red-300",
              @selected_room && @selected_room.id == room.id && "stroke-blue-500 stroke-2"
            ]}
          />
          <text
            :for={room <- @rooms}
            x={room.x + room.width / 2}
            y={room.y + room.height / 2}
            text-anchor="middle"
            dominant-baseline="middle"
            class="text-sm fill-gray-700 pointer-events-none"
          >
            {room.name}
          </text>
        </svg>

        <div :if={@selected_room} class="flex-1">
          <h3 class="font-bold text-lg">{@selected_room.name}</h3>
          <p>Status: {humanize_status(@selected_room.status)}</p>
          <.button :if={@selected_room.status == :available} phx-click="book_room">
            Book Room
          </.button>
        </div>
      </div>
    </Layouts.app>
    """
  end

  def handle_event("select_room", %{"id" => id}, socket) do
    room = Enum.find(socket.assigns.rooms, &(&1.id == id))
    {:noreply, assign(socket, :selected_room, room)}
  end

  def handle_event("book_room", _, socket) do
    room = socket.assigns.selected_room
    rooms = update_room_status(socket.assigns.rooms, room.id, :occupied)

    {:noreply,
     socket
     |> assign(:rooms, rooms)
     |> assign(:selected_room, %{room | status: :occupied})}
  end

  defp update_room_status(rooms, id, status) do
    Enum.map(rooms, fn
      %{id: ^id} = room -> %{room | status: status}
      room -> room
    end)
  end

  defp humanize_status(:available), do: "Available"
  defp humanize_status(:occupied), do: "Occupied"
end
```

### SVG with Click Coordinates

```elixir
defmodule MyAppWeb.DrawingLive do
  use MyAppWeb, :live_view

  def mount(_params, _session, socket) do
    {:ok,
     socket
     |> assign(:points, [])
     |> assign(:drawing, false)}
  end

  def render(assigns) do
    ~H"""
    <Layouts.app flash={@flash}>
      <div class="space-y-4">
        <div class="flex gap-4">
          <.button phx-click="clear">Clear</.button>
          <.button phx-click="toggle_drawing">
            {if @drawing, do: "Stop Drawing", else: "Start Drawing"}
          </.button>
        </div>

        <svg
          id="canvas"
          viewBox="0 0 800 600"
          class="w-full border rounded bg-white cursor-crosshair"
          phx-click="add_point"
          phx-hook="SvgCoordinates"
        >
          <%!-- Draw lines between points --%>
          <polyline
            :if={length(@points) > 1}
            points={points_to_string(@points)}
            fill="none"
            stroke="blue"
            stroke-width="2"
          />

          <%!-- Draw circles at each point --%>
          <circle
            :for={{x, y} <- @points}
            cx={x}
            cy={y}
            r="4"
            class="fill-blue-500"
          />
        </svg>
      </div>
    </Layouts.app>
    """
  end

  def handle_event("add_point", %{"x" => x, "y" => y}, socket) do
    if socket.assigns.drawing do
      point = {x, y}
      {:noreply, update(socket, :points, &(&1 ++ [point]))}
    else
      {:noreply, socket}
    end
  end

  def handle_event("toggle_drawing", _, socket) do
    {:noreply, update(socket, :drawing, &(!&1))}
  end

  def handle_event("clear", _, socket) do
    {:noreply, assign(socket, :points, [])}
  end

  defp points_to_string(points) do
    points
    |> Enum.map(fn {x, y} -> "#{x},#{y}" end)
    |> Enum.join(" ")
  end
end
```

```javascript
// Hook to get SVG coordinates (handles viewBox scaling)
Hooks.SvgCoordinates = {
  mounted() {
    this.el.addEventListener("click", (e) => {
      const svg = this.el
      const pt = svg.createSVGPoint()
      pt.x = e.clientX
      pt.y = e.clientY

      // Transform to SVG coordinate space
      const svgP = pt.matrixTransform(svg.getScreenCTM().inverse())

      this.pushEvent("add_point", {
        x: Math.round(svgP.x),
        y: Math.round(svgP.y)
      })
    })
  }
}
```

### Animated SVG with LiveView

```elixir
defmodule MyAppWeb.ProgressRingLive do
  use MyAppWeb, :live_view

  def mount(_params, _session, socket) do
    {:ok, assign(socket, progress: 0)}
  end

  def render(assigns) do
    # Calculate stroke-dasharray for progress ring
    circumference = 2 * :math.pi() * 45
    offset = circumference - (assigns.progress / 100) * circumference

    assigns = assign(assigns, circumference: circumference, offset: offset)

    ~H"""
    <Layouts.app flash={@flash}>
      <div class="flex flex-col items-center gap-8">
        <svg width="120" height="120" class="transform -rotate-90">
          <%!-- Background circle --%>
          <circle
            cx="60"
            cy="60"
            r="45"
            fill="none"
            stroke="#e5e7eb"
            stroke-width="10"
          />
          <%!-- Progress circle --%>
          <circle
            cx="60"
            cy="60"
            r="45"
            fill="none"
            stroke="#3b82f6"
            stroke-width="10"
            stroke-linecap="round"
            stroke-dasharray={@circumference}
            stroke-dashoffset={@offset}
            class="transition-all duration-300 ease-out"
          />
        </svg>

        <div class="text-2xl font-bold">{@progress}%</div>

        <input
          type="range"
          min="0"
          max="100"
          value={@progress}
          phx-change="update_progress"
          name="progress"
          class="w-64"
        />
      </div>
    </Layouts.app>
    """
  end

  def handle_event("update_progress", %{"progress" => progress}, socket) do
    {:noreply, assign(socket, progress: String.to_integer(progress))}
  end
end
```

## Range Sliders & Live Inputs

### Basic Range Slider

```elixir
defmodule MyAppWeb.VolumeControlLive do
  use MyAppWeb, :live_view

  def mount(_params, _session, socket) do
    {:ok, assign(socket, volume: 50)}
  end

  def render(assigns) do
    ~H"""
    <Layouts.app flash={@flash}>
      <div class="max-w-md mx-auto space-y-4">
        <label class="block">
          <span class="text-gray-700">Volume: {@volume}%</span>
          <input
            type="range"
            name="volume"
            min="0"
            max="100"
            value={@volume}
            phx-change="update_volume"
            phx-debounce="50"
            class="w-full h-2 bg-gray-200 rounded-lg appearance-none cursor-pointer"
          />
        </label>

        <div class="flex justify-between text-sm text-gray-500">
          <span>0%</span>
          <span>50%</span>
          <span>100%</span>
        </div>
      </div>
    </Layouts.app>
    """
  end

  def handle_event("update_volume", %{"volume" => volume}, socket) do
    {:noreply, assign(socket, volume: String.to_integer(volume))}
  end
end
```

### Dual Range Slider (Price Filter)

```elixir
defmodule MyAppWeb.PriceFilterLive do
  use MyAppWeb, :live_view

  @min_price 0
  @max_price 1000

  def mount(_params, _session, socket) do
    {:ok,
     socket
     |> assign(:min_value, @min_price)
     |> assign(:max_value, @max_price)
     |> assign(:min_price, @min_price)
     |> assign(:max_price, @max_price)
     |> load_products()}
  end

  def render(assigns) do
    ~H"""
    <Layouts.app flash={@flash}>
      <div class="max-w-2xl mx-auto space-y-8">
        <div class="space-y-4">
          <h2 class="font-bold">Price Range: ${@min_value} - ${@max_value}</h2>

          <div class="relative pt-6 pb-2">
            <%!-- Track --%>
            <div class="absolute top-8 left-0 right-0 h-2 bg-gray-200 rounded" />
            <%!-- Active range --%>
            <div
              class="absolute top-8 h-2 bg-blue-500 rounded"
              style={"left: #{percentage(@min_value)}%; right: #{100 - percentage(@max_value)}%;"}
            />

            <%!-- Min slider --%>
            <input
              type="range"
              name="min"
              min={@min_price}
              max={@max_price}
              value={@min_value}
              phx-change="update_min"
              phx-debounce="100"
              class="absolute w-full appearance-none bg-transparent pointer-events-none [&::-webkit-slider-thumb]:pointer-events-auto [&::-webkit-slider-thumb]:w-4 [&::-webkit-slider-thumb]:h-4 [&::-webkit-slider-thumb]:rounded-full [&::-webkit-slider-thumb]:bg-blue-600 [&::-webkit-slider-thumb]:appearance-none [&::-webkit-slider-thumb]:cursor-pointer"
            />

            <%!-- Max slider --%>
            <input
              type="range"
              name="max"
              min={@min_price}
              max={@max_price}
              value={@max_value}
              phx-change="update_max"
              phx-debounce="100"
              class="absolute w-full appearance-none bg-transparent pointer-events-none [&::-webkit-slider-thumb]:pointer-events-auto [&::-webkit-slider-thumb]:w-4 [&::-webkit-slider-thumb]:h-4 [&::-webkit-slider-thumb]:rounded-full [&::-webkit-slider-thumb]:bg-blue-600 [&::-webkit-slider-thumb]:appearance-none [&::-webkit-slider-thumb]:cursor-pointer"
            />
          </div>

          <div class="flex justify-between text-sm text-gray-500">
            <span>${@min_price}</span>
            <span>${@max_price}</span>
          </div>
        </div>

        <div class="grid grid-cols-3 gap-4">
          <div :for={product <- @products} class="border rounded p-4">
            <h3 class="font-semibold">{product.name}</h3>
            <p class="text-green-600">${product.price}</p>
          </div>
        </div>
      </div>
    </Layouts.app>
    """
  end

  def handle_event("update_min", %{"min" => min}, socket) do
    min = String.to_integer(min)
    # Ensure min doesn't exceed max
    min = min(min, socket.assigns.max_value - 10)

    {:noreply,
     socket
     |> assign(:min_value, min)
     |> load_products()}
  end

  def handle_event("update_max", %{"max" => max}, socket) do
    max = String.to_integer(max)
    # Ensure max doesn't go below min
    max = max(max, socket.assigns.min_value + 10)

    {:noreply,
     socket
     |> assign(:max_value, max)
     |> load_products()}
  end

  defp percentage(value) do
    (value - @min_price) / (@max_price - @min_price) * 100
  end

  defp load_products(socket) do
    products =
      Shop.list_products()
      |> Enum.filter(fn p ->
        p.price >= socket.assigns.min_value and p.price <= socket.assigns.max_value
      end)

    assign(socket, :products, products)
  end
end
```

### Color Picker with Multiple Sliders

```elixir
defmodule MyAppWeb.ColorPickerLive do
  use MyAppWeb, :live_view

  def mount(_params, _session, socket) do
    {:ok,
     socket
     |> assign(:red, 128)
     |> assign(:green, 128)
     |> assign(:blue, 128)}
  end

  def render(assigns) do
    hex_color = to_hex(assigns.red, assigns.green, assigns.blue)
    assigns = assign(assigns, :hex_color, hex_color)

    ~H"""
    <Layouts.app flash={@flash}>
      <div class="max-w-md mx-auto space-y-6">
        <div
          class="w-full h-32 rounded-lg border-2 border-gray-300"
          style={"background-color: #{@hex_color};"}
        />

        <div class="text-center font-mono text-lg">{@hex_color}</div>

        <.color_slider label="Red" name="red" value={@red} color="red" />
        <.color_slider label="Green" name="green" value={@green} color="green" />
        <.color_slider label="Blue" name="blue" value={@blue} color="blue" />

        <.button phx-click="randomize">Randomize</.button>
      </div>
    </Layouts.app>
    """
  end

  attr :label, :string, required: true
  attr :name, :string, required: true
  attr :value, :integer, required: true
  attr :color, :string, required: true

  defp color_slider(assigns) do
    ~H"""
    <div class="space-y-1">
      <div class="flex justify-between">
        <span class="text-gray-700">{@label}</span>
        <span class="font-mono">{@value}</span>
      </div>
      <input
        type="range"
        name={@name}
        min="0"
        max="255"
        value={@value}
        phx-change="update_color"
        phx-debounce="30"
        class={[
          "w-full h-2 rounded-lg appearance-none cursor-pointer",
          @color == "red" && "accent-red-500",
          @color == "green" && "accent-green-500",
          @color == "blue" && "accent-blue-500"
        ]}
      />
    </div>
    """
  end

  def handle_event("update_color", params, socket) do
    socket =
      Enum.reduce(params, socket, fn
        {"red", v}, s -> assign(s, :red, String.to_integer(v))
        {"green", v}, s -> assign(s, :green, String.to_integer(v))
        {"blue", v}, s -> assign(s, :blue, String.to_integer(v))
        _, s -> s
      end)

    {:noreply, socket}
  end

  def handle_event("randomize", _, socket) do
    {:noreply,
     socket
     |> assign(:red, :rand.uniform(256) - 1)
     |> assign(:green, :rand.uniform(256) - 1)
     |> assign(:blue, :rand.uniform(256) - 1)}
  end

  defp to_hex(r, g, b) do
    "#" <>
      Integer.to_string(r, 16) |> String.pad_leading(2, "0") <>
      Integer.to_string(g, 16) |> String.pad_leading(2, "0") <>
      Integer.to_string(b, 16) |> String.pad_leading(2, "0")
  end
end
```

### Slider with Custom Hook (Smooth Updates)

For very smooth slider updates, use a JS hook to batch updates:

```elixir
def render(assigns) do
  ~H"""
  <div
    id="smooth-slider"
    phx-hook="SmoothSlider"
    phx-update="ignore"
    data-value={@value}
  >
    <input
      type="range"
      min="0"
      max="100"
      value={@value}
      class="w-full"
    />
    <output class="block text-center">{@value}</output>
  </div>
  """
end

def handle_event("slider_update", %{"value" => value}, socket) do
  # Process the final or batched value
  {:noreply, assign(socket, :value, value)}
end
```

```javascript
Hooks.SmoothSlider = {
  mounted() {
    const input = this.el.querySelector("input")
    const output = this.el.querySelector("output")
    let timeout = null

    input.addEventListener("input", (e) => {
      // Update display immediately
      output.textContent = e.target.value

      // Debounce server updates
      clearTimeout(timeout)
      timeout = setTimeout(() => {
        this.pushEvent("slider_update", { value: parseInt(e.target.value) })
      }, 150)
    })
  }
}
```

### Form with Multiple Range Inputs

```elixir
defmodule MyAppWeb.SettingsLive do
  use MyAppWeb, :live_view

  def mount(_params, _session, socket) do
    settings = %{
      brightness: 75,
      contrast: 50,
      saturation: 50,
      blur: 0
    }

    {:ok, assign(socket, settings: settings, form: to_form(settings, as: "settings"))}
  end

  def render(assigns) do
    ~H"""
    <Layouts.app flash={@flash}>
      <.form for={@form} phx-change="update" phx-submit="save" class="max-w-md mx-auto space-y-6">
        <.range_input field={@form[:brightness]} label="Brightness" min={0} max={100} />
        <.range_input field={@form[:contrast]} label="Contrast" min={0} max={100} />
        <.range_input field={@form[:saturation]} label="Saturation" min={0} max={100} />
        <.range_input field={@form[:blur]} label="Blur" min={0} max={20} />

        <.button type="submit">Save Settings</.button>
      </.form>

      <div
        class="mt-8 w-64 h-64 bg-cover bg-center rounded"
        style={"
          background-image: url('/images/sample.jpg');
          filter: brightness(#{@settings.brightness}%)
                  contrast(#{@settings.contrast}%)
                  saturate(#{@settings.saturation}%)
                  blur(#{@settings.blur}px);
        "}
      />
    </Layouts.app>
    """
  end

  attr :field, Phoenix.HTML.FormField, required: true
  attr :label, :string, required: true
  attr :min, :integer, default: 0
  attr :max, :integer, default: 100

  defp range_input(assigns) do
    ~H"""
    <div class="space-y-1">
      <div class="flex justify-between text-sm">
        <label for={@field.id}>{@label}</label>
        <span class="font-mono">{@field.value}</span>
      </div>
      <input
        type="range"
        id={@field.id}
        name={@field.name}
        value={@field.value}
        min={@min}
        max={@max}
        phx-debounce="50"
        class="w-full"
      />
    </div>
    """
  end

  def handle_event("update", %{"settings" => params}, socket) do
    settings =
      Map.new(params, fn {k, v} -> {String.to_existing_atom(k), String.to_integer(v)} end)

    {:noreply, assign(socket, settings: settings, form: to_form(settings, as: "settings"))}
  end

  def handle_event("save", %{"settings" => params}, socket) do
    # Save to database
    {:noreply, put_flash(socket, :info, "Settings saved!")}
  end
end
```

## Anti-Patterns to Avoid

### Memory Bloat

```elixir
# BAD: Storing large list in assigns
def mount(_, _, socket) do
  {:ok, assign(socket, items: Repo.all(Item))}  # Memory grows!
end

# GOOD: Use streams
def mount(_, _, socket) do
  {:ok, stream(socket, :items, Repo.all(Item))}
end
```

### Blocking Operations

```elixir
# BAD: Blocking the socket
def handle_event("fetch", _, socket) do
  data = HTTPClient.get!(url)  # Blocks all events!
  {:noreply, assign(socket, data: data)}
end

# GOOD: Use async
def handle_event("fetch", _, socket) do
  {:noreply,
   socket
   |> assign(:loading, true)
   |> start_async(:fetch, fn -> HTTPClient.get!(url) end)}
end

def handle_async(:fetch, {:ok, data}, socket) do
  {:noreply, assign(socket, data: data, loading: false)}
end
```

### N+1 in Components

```elixir
# BAD: Query in component
def render(assigns) do
  user = Repo.get!(User, assigns.user_id)  # N+1!
  ~H"<div>{user.name}</div>"
end

# GOOD: Preload in parent
def mount(_, _, socket) do
  posts = Post |> preload(:author) |> Repo.all()
  {:ok, stream(socket, :posts, posts)}
end
```

### Missing Loading States

```elixir
# BAD: No feedback
<button phx-click="save">Save</button>

# GOOD: Show loading
<button phx-click="save" phx-disable-with="Saving...">
  Save
</button>
```

### Form Anti-Patterns

```elixir
# BAD: Accessing changeset in template
<%= for {field, errors} <- @changeset.errors do %>

# GOOD: Use form errors
<%= for error <- @form[:email].errors do %>

# BAD: let binding
<.form for={@form} let={f}>
  <.input field={f[:email]} />
</.form>

# GOOD: Direct access
<.form for={@form}>
  <.input field={@form[:email]} />
</.form>
```

### Stream Anti-Patterns

```elixir
# BAD: Trying to filter streams
filtered = Enum.filter(@streams.items, &(&1.active))  # Won't work!

# GOOD: Refetch and reset
def handle_event("filter", %{"active" => "true"}, socket) do
  items = Items.list_active()
  {:noreply, stream(socket, :items, items, reset: true)}
end

# BAD: Missing phx-update
<div id="items">
  <div :for={{dom_id, item} <- @streams.items} id={dom_id}>

# GOOD: Add phx-update="stream"
<div id="items" phx-update="stream">
  <div :for={{dom_id, item} <- @streams.items} id={dom_id}>
```

### Navigation Anti-Patterns

```elixir
# BAD: Deprecated functions
live_redirect(socket, to: path)
live_patch(socket, to: path)

# GOOD: Use push_ functions
push_navigate(socket, to: path)
push_patch(socket, to: path)

# BAD: In template
<%= live_redirect "Link", to: path %>

# GOOD: Use .link component
<.link navigate={path}>Link</.link>
```
