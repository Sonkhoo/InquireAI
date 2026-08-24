create extension if not exists "uuid-ossp";
--roles
create table if not exists roles (
    role_name varchar(50) unique not null primary key,
    created_at timestamp default current_timestamp
);
insert into roles (role_name) values ('user') on conflict do nothing;;
insert into roles (role_name) values ('hr') on conflict do nothing;;
insert into roles (role_name) values ('admin') on conflict do nothing;;
insert into roles (role_name) values ('engineer') on conflict do nothing;;
insert into roles (role_name) values ('marketer') on conflict do nothing;;


--users
create table if not exists users (
    id uuid primary key default uuid_generate_v4(),
    email varchar(255) unique not null,
    display_name varchar(255) not null,
    password varchar(255) not null,
    role varchar(50) references roles(role_name) default 'user',
    workspace_id uuid references workspaces(id) on delete set null,
    created_at timestamptz default current_timestamp
);
--workspaces
create table if not exists workspaces (
    id uuid primary key default uuid_generate_v4(),
    name varchar(255) not null,
    description text,
    created_at timestamptz default current_timestamp
);

--conversations
create table if not exists conversations (
    id uuid primary key default uuid_generate_v4(),
    user_id uuid references users(id) on delete cascade,
    workspace_id uuid references workspaces(id) on delete cascade,
    title varchar(255) not null,
    created_at timestamptz default current_timestamp,
    updated_at timestamptz default current_timestamp
);

--messages
create table if not exists messages (
    id uuid primary key default uuid_generate_v4(),
    conversation_id uuid references conversations(id) on delete cascade,
    role text not null check (role in ('user', 'assistant', 'system')),
    content text not null,
    metadata jsonb,
    created_at timestamptz default current_timestamp
);
create index if not exists idx_messages_conversation_id on messages(conversation_id, created_at);

-- Demo users (auth is skipped for the demo — the frontend picks one of these
-- via a dropdown and the API trusts the email + looks up the role here).
-- One admin (can ingest), one allowed role (engineer), one disallowed role (marketer).
insert into users (id, email, display_name, password, role)
values
    ('00000000-0000-0000-0000-000000000001', 'john@inquire.ai', 'John', 'dev-only', 'admin'),
    ('00000000-0000-0000-0000-000000000002', 'alice@inquire.ai', 'Alice', 'dev-only', 'engineer'),
    ('00000000-0000-0000-0000-000000000003', 'bob@inquire.ai', 'Bob', 'dev-only', 'marketer')
on conflict (id) do nothing;

insert into workspaces (id, name)
values
    ('11111111-1111-1111-1111-111111111111', 'Demo Workspace'),
    ('22222222-2222-2222-2222-222222222222', 'Engineering'),
    ('33333333-3333-3333-3333-333333333333', 'Finance'),
    ('44444444-4444-4444-4444-444444444444', 'HR')
on conflict (id) do nothing;